from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Sequence, TypedDict, cast

from assetextractor.conversion.statistics.icon_processor import IconProcessor
from assetextractor.parsing.core.texts import StandardTextConverter
from assetextractor.parsing.typed.common.asset_pool_base import AssetPoolBase
from assetextractor.parsing.typed.common.enums import RarityVisualization
from assetextractor.parsing.typed.item import Item, ItemWithBoost

if TYPE_CHECKING:
    from assetextractor.parsing.core.assets import Asset, AssetCache
    from assetextractor.parsing.typed.buffs import BuffKey
    from assetextractor.parsing.typed.common.upgrades.building_upgrade import WorkforceUpgradeJSON
    from assetextractor.parsing.typed.common.upgrades.factory_upgrade import AddedFertilityJSON
    from assetextractor.parsing.typed.common.upgrades.maintenance_upgrade import ReplacementWorkforceJSON
    from assetextractor.parsing.typed.common.upgrades.residence_upgrade import ProductNeedUpgradeJSON
    from assetextractor.parsing.typed.effect import Effect

# Safely import IPython's display for Jupyter Notebook integration
try:
    from IPython.display import HTML, display  # type: ignore
except ImportError:
    display, HTML = None, None  # type: ignore


# --- Strictly Typed JSON Schemas ---


class ProductRefJSON(TypedDict):
    guid: int
    title: str


class ModifierUpgradeAttributeJSON(TypedDict):
    key: str
    label: str
    value: str
    raw: float
    # target_guid: int | None
    product_needs: List[ProductRefJSON]
    """The formatted requirement 'Product' needs that the 'ResidenceUpgrade' applies."""


class AdditionalWorkforceJSON(TypedDict):
    guid: int
    title: str
    # target_guid: int | None


class ModifierResult(TypedDict):
    attributes: List[ModifierUpgradeAttributeJSON]
    added_fertility: AddedFertilityJSON | None
    workforce_replacement: ReplacementWorkforceJSON | None
    additional_workforces: List[WorkforceUpgradeJSON] | None
    product_upgrades: List[ProductNeedUpgradeJSON] | None
    additional_fun_effect: Effect | None
    workforce_modifier_in_percent: str | None


class BuffModifierJSON(TypedDict):
    guid: int
    name: str
    label: str
    template: str
    attributes: List[ModifierUpgradeAttributeJSON]
    additional_workforces: List[AdditionalWorkforceJSON]
    workforce_replacement: ReplacementWorkforceJSON | None
    added_fertility: AddedFertilityJSON | None
    nested_functional_effect: SpecialistEffectJSON | None
    workforce_modifier_in_percent: str | None


class AffectedItemJSON(TypedDict):
    guid: int
    title: str


class TargetAssetJSON(TypedDict):
    guid: int
    name: str
    title: str
    asset_pool_guid: int | None
    asset_pool_title: str | None
    affected_items: List[AffectedItemJSON]


class SpecialistEffectJSON(TypedDict):
    scope: str
    category: str
    targets: List[TargetAssetJSON]
    buffs: List[BuffModifierJSON]


class SpecialistBoostJSON(TypedDict):
    condition: str
    hint: str
    buffs: List[BuffModifierJSON]


class SpecialistItemJSON(TypedDict):
    guid: int
    name: str
    title: str
    description: str
    icon_url: str
    rarity: str
    niche: str
    allocation: str
    trade_price: int
    origin: str
    has_boost: bool
    boost_details: SpecialistBoostJSON | None
    effect: SpecialistEffectJSON | None


# --- Simplified Export Schemas ---


class SimplifiedAttribute(TypedDict):
    key: str
    value: str
    product_needs: List[int]


class SimplifiedBuff(TypedDict):
    guid: int
    target_guids: List[int]
    attributes: List[SimplifiedAttribute]
    additional_workforces: List[int]
    added_fertility: AddedFertilityJSON | None  # Keeps the structure from AddedFertilityJSON
    workforce_replacement: ReplacementWorkforceJSON | None  # Keeps the structure from ReplacementWorkforceJSON
    workforce_modifier_in_percent: str | None


class SimplifiedTarget(TypedDict):
    guid: int
    asset_pool_guid: int | None
    asset_pool_title: str | None
    affected_items: List[int]


class SimplifiedEffect(TypedDict):
    scope: str
    category: str
    targets: List[SimplifiedTarget]
    buffs: List[SimplifiedBuff]


class SimplifiedBoost(TypedDict):
    condition: str
    hint: str
    buffs: List[SimplifiedBuff]


class SimplifiedSpecialist(TypedDict):
    icon_url: str
    title: str
    description: str
    rarity: str
    niche: str
    allocation: str
    has_boost: bool
    boost_details: SimplifiedBoost | None
    effect: SimplifiedEffect


# The final container for your JSON dump
SimplifiedDataDict = Dict[str, SimplifiedSpecialist]


@dataclass
class SpecialistCollection:
    """Container for categorized and sorted game assets."""

    items: Dict[int, Item] = field(default_factory=lambda: cast("Dict[int, Item]", {}))
    items_with_boost: Dict[int, ItemWithBoost] = field(default_factory=lambda: cast("Dict[int, ItemWithBoost]", {}))


class SpecialistExtractor:
    """Main orchestrator for extracting items from Anno 117 assets."""

    # Dynamic format variable controlling visual separation lines globally
    DEFAULT_PRINT_WIDTH = 100

    @staticmethod
    def __is_asset_pool_tpl(tpl_name: str) -> bool:
        return tpl_name in ["AssetPoolNamed", "AssetPool"]

    def __init__(self, assets: AssetCache, language: str = "english"):
        """Initialize the specialists extractor.

        Args:
            assets: Asset cache with loaded assets
            language: Language for text localization (default: "english")
        """
        self.assets = assets
        self.language = language
        self.texts = assets.texts
        self.specialists = SpecialistCollection()
        self.print_width = self.DEFAULT_PRINT_WIDTH

    def _prepare_converter(self):
        """Ensures the shared cache is using this extractor's language."""
        self.assets.texts.converter = StandardTextConverter(self.language)

    def extract_all(self) -> SpecialistCollection:
        """
        Extracts all 'Item' and 'ItemWithBoost' assets, separates them,
        and saves them sorted by GUID into self.specialists.

        Returns:
            SpecialistCollection: The populated dataclass instance.
        """
        self._prepare_converter()

        tpl_item = self.assets.templates.get("Item")
        tpl_item_boost = self.assets.templates.get("ItemWithBoost")

        # If neither template exists, reset and return empty structure
        if not tpl_item and not tpl_item_boost:
            self.specialists = SpecialistCollection()
            return self.specialists

        # Gather assets from available templates safely
        all_assets: List[Asset] = []
        if tpl_item:
            all_assets.extend(tpl_item.assets)
        if tpl_item_boost:
            all_assets.extend(tpl_item_boost.assets)

        # Separate and map raw assets by type
        raw_items: Dict[int, Item] = {}
        raw_boosts: Dict[int, ItemWithBoost] = {}

        for a in all_assets:
            match a.template.name:
                case "ItemWithBoost":
                    raw_boosts[a.guid] = cast("ItemWithBoost", a)
                case "Item":
                    # Filter out test items.
                    if a.guid in [95752, 95753, 95764]:
                        continue
                    raw_items[a.guid] = cast("Item", a)
                case _:
                    pass

        # Sort by GUID and lock the order into the respective dictionaries
        sorted_items = {guid: raw_items[guid] for guid in sorted(raw_items.keys())}
        sorted_boosts = {guid: raw_boosts[guid] for guid in sorted(raw_boosts.keys())}

        # Instantiate and save to self.specialists
        self.specialists = SpecialistCollection(items=sorted_items, items_with_boost=sorted_boosts)

        return self.specialists

    # --- Serialization Methods ---

    def _serialize_single_buff_modifiers(self, buff_asset: Asset) -> BuffModifierJSON:
        """Inspects a buff asset and aggregates all active component modifiers dynamically."""
        attributes: List[ModifierUpgradeAttributeJSON] = []
        additional_workforces: List[AdditionalWorkforceJSON] = []
        workforce_repl: ReplacementWorkforceJSON | None = None
        added_fertility_data: AddedFertilityJSON | None = None
        nested_effect_data: SpecialistEffectJSON | None = None
        workforce_mod: str | None = None

        # List all the serialize modifiers methods.
        modifier_methods = [
            "serialize_building_modifiers",
            "serialize_factory_modifiers",
            "serialize_health_modifiers",
            "serialize_maintenance_modifiers",
            "serialize_movement_modifiers",
            "serialize_residence_modifiers",
            "serialize_trade_ship_modifiers",
            "serialize_unit_modifiers",
            "serialize_vehicle_modifiers",
            "serialize_area_buff_modifiers",
        ]

        for method_name in modifier_methods:
            if hasattr(buff_asset, method_name):
                # 1. Get the method
                method = getattr(buff_asset, method_name)

                # 2. Call it and cast to our TypedDict so the type checker
                #    knows the return structure
                res = cast("ModifierResult", method())

                # If this is serialize_residence_modifiers, capture product reference if present
                product_refs: List[ProductRefJSON] = []
                if (
                    method_name == "serialize_residence_modifiers"
                    and "product_upgrades" in res
                    and res["product_upgrades"]
                ):
                    product_refs = [{"guid": p["guid"], "title": p["title"]} for p in res["product_upgrades"]]

                # 3. Extend attributes safely
                if "attributes" in res:
                    for attr in res["attributes"]:
                        attributes.append(
                            {
                                "key": attr["key"],
                                "label": attr["label"],
                                "value": attr["value"],
                                "raw": attr["raw"],
                                "product_needs": product_refs,
                            }
                        )

                # 4. Handle specific component side-effects
                if "additional_workforces" in res and res["additional_workforces"] is not None:
                    for wf in res["additional_workforces"]:
                        additional_workforces.append({"guid": wf["guid"], "title": wf["title"]})

                if "added_fertility" in res:
                    added_fertility_data = res["added_fertility"]
                if "workforce_replacement" in res:
                    workforce_repl = res["workforce_replacement"]
                if "workforce_modifier_in_percent" in res:
                    workforce_mod = res["workforce_modifier_in_percent"]

                # Check if this result contains a nested effect from BuildingUpgrade
                if "additional_fun_effect" in res and res["additional_fun_effect"] is not None:
                    effect_obj = res["additional_fun_effect"]
                    # Serialize targets and buffs using existing methods
                    serialized_targets = self._serialize_targets(effect_obj.targets)
                    serialized_buffs = [self._serialize_single_buff_modifiers(buff) for buff in effect_obj.buffs]

                    nested_effect_data = {
                        "scope": effect_obj.effect_info.effect_scope,
                        "category": effect_obj.effect_info.source_category,
                        "targets": serialized_targets,
                        "buffs": serialized_buffs,
                    }

        buff_label = buff_asset.text() if buff_asset.text else buff_asset.name
        return {
            "guid": buff_asset.guid,
            "name": buff_asset.name,
            "label": buff_label,
            "template": buff_asset.template.name,
            "attributes": attributes,
            "additional_workforces": additional_workforces,
            "workforce_replacement": workforce_repl,
            "added_fertility": added_fertility_data,
            "nested_functional_effect": nested_effect_data,
            "workforce_modifier_in_percent": workforce_mod,
        }

    def _serialize_targets(self, targets_sequence: Sequence[Asset]) -> List[TargetAssetJSON]:
        return [self._build_target_node(target) for target in targets_sequence]

    def _get_flattened_affected_items(self, asset: Asset) -> List[AffectedItemJSON]:
        """Recursively flattens an asset pool to return only the inner leaf assets."""
        items: List[AffectedItemJSON] = []
        if isinstance(asset, AssetPoolBase):
            for sub_asset in asset.asset_pool_list:
                items.extend(self._get_flattened_affected_items(sub_asset))
        else:
            items.append({"guid": asset.guid, "title": asset.text() if asset.text else asset.name})
        return items

    def _build_target_node(self, target_asset: Asset) -> TargetAssetJSON:
        is_asset_pool = self.__is_asset_pool_tpl(target_asset.template.name)
        return {
            "guid": target_asset.guid,
            "name": target_asset.name,
            "title": target_asset.text() if target_asset.text else target_asset.name,
            "asset_pool_guid": target_asset.guid if is_asset_pool else None,
            "asset_pool_title": (target_asset.text() if target_asset.text else target_asset.name)
            if is_asset_pool
            else None,
            "affected_items": self._get_flattened_affected_items(target_asset),
        }

    # --- Printing Methods ---

    def print_specialists(self, guid: int | None = None) -> None:
        """
        Prints details for stored specialists.

        Args:
            guid: If provided, only prints that specific specialist.
                  If None, prints all stored specialists.
        """
        if not self.specialists.items and not self.specialists.items_with_boost:
            print("No specialists loaded in memory. Call extract_all() first.")
            return

        # Combine both dictionaries and print them sorted by key
        all_specialists = {**self.specialists.items, **self.specialists.items_with_boost}
        if guid is not None:
            if specialist := all_specialists.get(guid):
                self._print_single_specialist(specialist)
            else:
                print(f"Specialist with GUID {guid} not found in current results.")
        else:
            for guid in sorted(all_specialists.keys()):
                self._print_single_specialist(all_specialists[guid])

    def _print_single_specialist(self, item: Item) -> None:
        """Internal helper to format and print the properties of a single specialist."""
        is_boost = isinstance(item, ItemWithBoost)
        type_label = "SPECIALIST (WITH BOOST)" if is_boost else "SPECIALIST"

        print(f"\n{'=' * self.print_width}")
        print(f"{type_label}: {item.item_standard_info.title} (GUID: {item.guid}) ".center(self.print_width))
        print(f"{'=' * self.print_width}")

        std_name = item.item_standard_info.std_name
        description = item.item_standard_info.description

        rendered_side_by_side = False
        if display is not None and HTML is not None:
            icon_data = IconProcessor.get_icon_package(item, include_image=True)
            img = icon_data.get("image")
            if img is not None:
                import base64

                b64_data = None
                mime_type = "image/png"

                # Extract raw bytes from the object's rich-display representation hooks
                for attr, mime in [
                    ("_repr_png_", "image/png"),
                    ("_repr_webp_", "image/webp"),
                    ("_repr_jpeg_", "image/jpeg"),
                ]:
                    if hasattr(img, attr):
                        try:
                            raw_bytes = getattr(img, attr)()
                            if raw_bytes:
                                b64_data = base64.b64encode(raw_bytes).decode("utf-8")
                                mime_type = mime
                                break
                        except Exception:
                            pass

                if b64_data:
                    # Dynamic theme-aware side-by-side flexbox layout
                    html_content = f"""
                    <div style="display: flex; align-items: flex-start; gap: 16px; margin: 12px 0; font-family: var(--jp-ui-font-family, sans-serif); color: var(--jp-ui-font-color1, #111);">
                        <div style="flex-shrink: 0; width: 64px; height: 64px; border: 1px solid var(--jp-border-color2, #ccc); border-radius: 4px; overflow: hidden; background: #2a2a2a; display: flex; align-items: center; justify-content: center;">
                            <img src="data:{mime_type};base64,{b64_data}" style="width: 64px; height: 64px; object-fit: contain;" />
                        </div>
                        <div style="display: flex; flex-direction: column; justify-content: center; min-height: 64px; line-height: 1.5;">
                            <div><strong style="color: var(--jp-ui-font-color2, #444);">Standard Name:</strong> {std_name}</div>
                            <div style="margin-top: 2px;"><strong style="color: var(--jp-ui-font-color2, #444);">Description:</strong> <span style="font-style: italic; color: var(--jp-ui-font-color3, #666);">{description}</span></div>
                        </div>
                    </div>
                    """
                    display(HTML(html_content))
                    rendered_side_by_side = True

        # Fallback to normal stacked text/image print if running outside a notebook
        if not rendered_side_by_side:
            if display is not None:
                icon_data = IconProcessor.get_icon_package(item, include_image=True)
                if img := icon_data.get("image"):
                    display(img, metadata={"image/png": {"width": 64, "height": 64}})
            print(f"Standard Name: {std_name}")
            print(f"Description:   {description}")

        print(f"{'-' * self.print_width}")

        info = item.item_info
        print(f"Allocation:    {info.allocation.value if hasattr(info.allocation, 'value') else info.allocation}")
        print(f"Rarity:        {info.rarity.value if hasattr(info.rarity, 'value') else info.rarity}")
        print(f"Niche:         {info.niche.value if hasattr(info.niche, 'value') else info.niche}")
        print(f"Trade Price:   {info.trade_price}")
        print(f"Origin:        {info.origin.value if hasattr(info.origin, 'value') else info.origin}")

        if is_boost:
            print(f"{'-' * self.print_width}")
            item.print_boost_info(prefix="     ")
            print(f"{'-' * self.print_width}")

        # We pass a starting branch to frame the buffs
        item.print_buffs(item.buffs, prefix="     ")

        # If we have a production chain mapping context (e.g., for Patrons/Effects), pass it here;
        # otherwise, pass an empty dictionary `{}` for specialists
        item.print_targets(item.targets, {}, prefix="     ")

        print(f"{'=' * self.print_width}")

    # --- Export Methods ---

    def export_simplified_json(
        self, output_path: Path | str, web_base_path: str | None = None, flatten: bool = True
    ) -> None:
        """
        Exports a minimalist JSON representation where nested GUIDs, templates,
        and name properties are stripped.
        """
        simplified_data: SimplifiedDataDict = {}

        all_specs = list(self.specialists.items.values()) + list(self.specialists.items_with_boost.values())

        for item in all_specs:
            # Filter out those specialist by rarity (unused rarities: Quest, Narrative & Uncommon)
            if item.item_info.rarity in [
                RarityVisualization.QUEST,
                RarityVisualization.UNCOMMON,
                RarityVisualization.NARRATIVE,
            ]:
                continue

            item_icon = IconProcessor.get_icon_package(item)

            simplified_data[str(item.guid)] = {
                "icon_url": IconProcessor.get_final_url(
                    raw_path=item_icon["path"],
                    canon_name=item_icon["canon_name"],
                    web_base_path=web_base_path,
                    flatten=flatten,
                    default_name=item.canonical_name,
                ),
                "title": item.item_standard_info.title,
                "description": item.item_standard_info.description,
                "rarity": item.item_info.rarity,
                "niche": item.item_info.niche,
                "allocation": item.item_info.allocation,
                "has_boost": isinstance(item, ItemWithBoost),
                "boost_details": None,
                "effect": {
                    "scope": item.effect_info.effect_scope,
                    "category": item.effect_info.source_category,
                    "targets": [
                        {
                            "guid": t.guid,
                            "asset_pool_guid": t.guid if self.__is_asset_pool_tpl(t.template.name) else None,
                            "asset_pool_title": (t.text() if t.text else t.name)
                            if self.__is_asset_pool_tpl(t.template.name)
                            else None,
                            "affected_items": [i["guid"] for i in self._get_flattened_affected_items(t)],
                        }
                        for t in item.targets
                    ],
                    "buffs": [],
                },
            }

            main_target_guids = [t.guid for t in item.targets]

            def process_buff_entry(b: BuffKey, target_buff_list: List[SimplifiedBuff]) -> None:
                serialized_buff = self._serialize_single_buff_modifiers(b)

                buff_entry: SimplifiedBuff = {
                    "guid": serialized_buff["guid"],
                    "target_guids": main_target_guids,
                    "attributes": [
                        {
                            "key": attr["key"],
                            "value": attr["value"],
                            "product_needs": [p["guid"] for p in attr["product_needs"]],
                        }
                        for attr in serialized_buff["attributes"]
                    ],
                    "additional_workforces": [w["guid"] for w in serialized_buff["additional_workforces"]],
                    "added_fertility": serialized_buff["added_fertility"],
                    "workforce_replacement": serialized_buff["workforce_replacement"],
                    "workforce_modifier_in_percent": serialized_buff.get("workforce_modifier_in_percent"),
                }

                target_buff_list.append(buff_entry)

                nested_effect = serialized_buff.get("nested_functional_effect")
                if nested_effect:
                    nested_target_guids = [nt["guid"] for nt in nested_effect["targets"]]

                    existing_target_guids = {t["guid"] for t in simplified_data[str(item.guid)]["effect"]["targets"]}
                    for nt in nested_effect["targets"]:
                        if nt["guid"] not in existing_target_guids:
                            simplified_data[str(item.guid)]["effect"]["targets"].append(
                                {
                                    "guid": nt["guid"],
                                    "asset_pool_guid": nt.get("asset_pool_guid"),
                                    "asset_pool_title": nt.get("asset_pool_title"),
                                    "affected_items": [ai["guid"] for ai in nt["affected_items"]],
                                }
                            )
                            existing_target_guids.add(nt["guid"])

                    for nb in nested_effect["buffs"]:
                        nested_buff_entry: SimplifiedBuff = {
                            "guid": nb["guid"],
                            "target_guids": nested_target_guids,
                            "attributes": [
                                {
                                    "key": attr["key"],
                                    "value": attr["value"],
                                    "product_needs": [p["guid"] for p in attr["product_needs"]],
                                }
                                for attr in nb["attributes"]
                            ],
                            "additional_workforces": [w["guid"] for w in nb["additional_workforces"]],
                            "added_fertility": nb["added_fertility"],
                            "workforce_replacement": nb["workforce_replacement"],
                            "workforce_modifier_in_percent": nb.get("workforce_modifier_in_percent"),
                        }
                        target_buff_list.append(nested_buff_entry)

            for b in item.buffs:
                process_buff_entry(b, simplified_data[str(item.guid)]["effect"]["buffs"])

            if isinstance(item, ItemWithBoost):
                b_info = item.boost_info
                boost_details: SimplifiedBoost = {
                    "condition": b_info.boost_condition,
                    "hint": b_info.boost_hint,
                    "buffs": [],
                }
                simplified_data[str(item.guid)]["boost_details"] = boost_details
                for b in b_info.boost_buffs:
                    process_buff_entry(b, boost_details["buffs"])

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(simplified_data, f, indent=4)

        print(f"Simplified export completed to {output_path}")

    def export_assets_index_json(
        self, output_path: Path, web_base_path: str | None = None, flatten: bool = True
    ) -> None:
        """
        Exports an index of all referenced affected items, workforce replacements,
        and additional workforces as a JSON dictionary mapping GUIDs to
        metadata (name and icon_url).
        """
        assets_registry: Dict[str, Dict[str, str]] = {}

        def register(guid: int, title: str, asset: Asset | None = None) -> None:
            if str(guid) in assets_registry:
                return

            icon_url = "N/A"
            if asset:
                icon_data = IconProcessor.get_icon_package(asset)
                icon_url = IconProcessor.get_final_url(
                    raw_path=icon_data["path"],
                    canon_name=icon_data["canon_name"],
                    web_base_path=web_base_path,
                    flatten=flatten,
                    default_name=asset.name,
                )

            assets_registry[str(guid)] = {"name": title, "icon_url": icon_url}

        # Traverse all specialists
        all_specs = list(self.specialists.items.values()) + list(self.specialists.items_with_boost.values())

        for item in all_specs:
            # 1. Affected Items (Targets)
            for target in item.targets:
                leaf_items = self._get_flattened_affected_items(target)
                for leaf in leaf_items:
                    # Attempt to retrieve asset object via cache
                    asset = self.assets.get(leaf["guid"])
                    register(leaf["guid"], leaf["title"], asset)

            # 2. Buffs
            for buff in item.buffs:
                serialized = self._serialize_single_buff_modifiers(buff)

                # Additional Workforces
                for aw in serialized["additional_workforces"]:
                    asset = self.assets.get(aw["guid"])
                    register(aw["guid"], aw["title"], asset)

                # Workforce Replacement
                wr = serialized["workforce_replacement"]
                if wr:
                    # Assuming ReplacementWorkforceJSON has 'guid' and 'title' keys
                    ow_asset = cast("Asset | None", self.assets.get(wr["old_workforce_guid"]))
                    nw_asset = cast("Asset | None", self.assets.get(wr["new_workforce_guid"]))

                    if ow_asset:
                        register(ow_asset.guid, ow_asset.text() if ow_asset.text else ow_asset.name, ow_asset)

                    if nw_asset:
                        register(nw_asset.guid, nw_asset.text() if nw_asset.text else nw_asset.name, nw_asset)

                # Product Needs.
                for attr in serialized["attributes"]:
                    for pn in attr.get("product_needs", []):
                        asset = self.assets.get(pn["guid"])
                        register(pn["guid"], pn["title"], asset)

                # Additional Functional Effect Items (Targets)
                nfe = serialized["nested_functional_effect"]
                if nfe:
                    for nfe_target in nfe["targets"]:
                        leaf_nfe_items = nfe_target["affected_items"]
                        for leaf in leaf_nfe_items:
                            # Attempt to retrieve asset object via cache
                            asset = self.assets.get(leaf["guid"])
                            register(leaf["guid"], leaf["title"], asset)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(assets_registry, f, indent=4)
        print(f"Asset index exported to {output_path}")

    def to_json_dict(self, web_base_path: str | None = None, flatten: bool = True) -> Dict[str, SpecialistItemJSON]:
        output_dict: Dict[str, SpecialistItemJSON] = {}

        all_specs: List[tuple[Item | ItemWithBoost, bool]] = []
        for item in self.specialists.items.values():
            all_specs.append((item, False))
        for item_boost in self.specialists.items_with_boost.values():
            all_specs.append((item_boost, True))

        all_specs.sort(key=lambda x: x[0].guid)

        for item, has_boost in all_specs:
            # Filter out those specialist by rarity (unused rarities: Quest, Narrative & Uncommon)
            if item.item_info.rarity in [
                RarityVisualization.QUEST,
                RarityVisualization.UNCOMMON,
                RarityVisualization.NARRATIVE,
            ]:
                continue

            std = item.item_standard_info
            info = item.item_info
            eff_info = item.effect_info
            item_icon = IconProcessor.get_icon_package(item)

            serialized_targets = self._serialize_targets(item.targets)

            # Map buffs dynamically, linking attributes contextually to their targets and products
            serialized_buffs: List[BuffModifierJSON] = [
                self._serialize_single_buff_modifiers(buff) for buff in item.buffs
            ]

            effect_data: SpecialistEffectJSON = {
                "scope": eff_info.effect_scope,
                "category": eff_info.source_category,
                "targets": serialized_targets,
                "buffs": serialized_buffs,
            }

            boost_details: SpecialistBoostJSON | None = None
            if has_boost and isinstance(item, ItemWithBoost):
                b_info = item.boost_info
                boost_details = {
                    "condition": b_info.boost_condition,
                    "hint": b_info.boost_hint,
                    "buffs": [self._serialize_single_buff_modifiers(b) for b in b_info.boost_buffs],
                }

            output_dict[str(item.guid)] = {
                "guid": item.guid,
                "name": std.std_name,
                "title": std.title,
                "description": std.description,
                "icon_url": IconProcessor.get_final_url(
                    raw_path=item_icon["path"],
                    canon_name=item_icon["canon_name"],
                    web_base_path=web_base_path,
                    flatten=flatten,
                    default_name=item.canonical_name,
                ),
                "rarity": info.rarity,
                "niche": info.niche,
                "allocation": info.allocation,
                "trade_price": info.trade_price,
                "origin": info.origin,
                "has_boost": has_boost,
                "boost_details": boost_details,
                "effect": effect_data,
            }

        return output_dict

    def save_to_json(self, file_path: Path | str, web_base_path: str | None = None, flatten: bool = True) -> None:
        """
        Helper to write the exported dictionary to a physical file.

        Args:
            file_path: Where to save the actual .json file.
            web_base_path: The URL prefix to use for images inside the JSON.
            flatten: If True, uses canon_name. If False, uses the full
                mirrored relative path.
        """
        data = self.to_json_dict(web_base_path=web_base_path, flatten=flatten)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"Successfully exported {len(data)} patrons to {file_path}")

    def export_all_assets(
        self,
        output_base: Path | str,
        quality: int = 75,
        resize: tuple[int, int] | None = (128, 128),
        flatten: bool = False,
        export_ref_assets: bool = False,
    ) -> None:
        """
        Exports all item-related assets.

        Args:
            output_base: The base physical directory where icons will be exported.
            quality: Compression ratio parameter for WebP (1-100). Default is 75.
            resize: Sizing dimension tuple. Default is (128, 128).
            flatten: True to save directly under output_base, False to preserve hierarchy.
        """
        output_path = Path(output_base)
        standard_assets: List[Asset] = []

        for specialist in self.specialists.items.values():
            standard_assets.append(specialist)
        for specialist in self.specialists.items_with_boost.values():
            standard_assets.append(specialist)

        # Batch export all standard icons at 128x128

        print(f"Exporting {len(standard_assets)} specialist icons...")
        IconProcessor.export_icons(
            assets=standard_assets,
            output_base=output_path,
            flatten=flatten,
            quality=quality,
            resize=resize,
            use_canonical_name=True,
        )
        print(f"Finished exporting {len(standard_assets)} specialist icons.")

        # Only export reference asset icons if allowed.
        if export_ref_assets:
            print("Seeding reference assets registry...")
            # Store the guid already visited to de-duplicate data.
            assets_registry: List[int] = []
            ref_assets: List[Asset] = []

            def register(guid: int, asset: Asset | None = None) -> None:
                if guid in assets_registry:
                    return

                if asset:
                    ref_assets.append(asset)

                assets_registry.append(guid)

            # Traverse all specialists
            all_specs = list(self.specialists.items.values()) + list(self.specialists.items_with_boost.values())

            for item in all_specs:
                # 1. Affected Items (Targets)
                for target in item.targets:
                    leaf_items = self._get_flattened_affected_items(target)
                    for leaf in leaf_items:
                        # Attempt to retrieve asset object via cache
                        asset = self.assets.get(leaf["guid"])
                        register(leaf["guid"], asset)

                # 2. Buffs
                for buff in item.buffs:
                    serialized = self._serialize_single_buff_modifiers(buff)

                    # Additional Workforces
                    for aw in serialized["additional_workforces"]:
                        asset = self.assets.get(aw["guid"])
                        register(aw["guid"], asset)

                    # Workforce Replacement
                    wr = serialized["workforce_replacement"]
                    if wr:
                        # Assuming ReplacementWorkforceJSON has 'guid' and 'title' keys
                        ow_asset = cast("Asset | None", self.assets.get(wr["old_workforce_guid"]))
                        nw_asset = cast("Asset | None", self.assets.get(wr["new_workforce_guid"]))

                        if ow_asset:
                            register(ow_asset.guid, ow_asset)

                        if nw_asset:
                            register(nw_asset.guid, nw_asset)

                    # Product Needs (New)
                    for attr in serialized["attributes"]:
                        for pn in attr.get("product_needs", []):
                            asset = self.assets.get(pn["guid"])
                            register(pn["guid"], asset)

                    # Additional Functional Effect Items (Targets)
                    nfe = serialized["nested_functional_effect"]
                    if nfe:
                        for nfe_target in nfe["targets"]:
                            leaf_nfe_items = nfe_target["affected_items"]
                            for leaf in leaf_nfe_items:
                                # Attempt to retrieve asset object via cache
                                asset = self.assets.get(leaf["guid"])
                                register(leaf["guid"], asset)

            # Export all reference assets.
            print(f"Exporting {len(ref_assets)} reference asset icons...")
            IconProcessor.export_icons(
                assets=ref_assets,
                output_base=output_path,
                flatten=flatten,
                quality=quality,
                resize=resize,
                use_canonical_name=True,
            )
            print(f"Finished exporting {len(ref_assets)} reference asset icons...")
