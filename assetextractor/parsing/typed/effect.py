from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, List  # Postpones evaluation of annotations

from assetextractor.parsing.core.asset_factories.asset_pool_named import AssetPoolNamed
from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.attributes import ListAttribute, ReferenceAttribute

# Import AssetCache ONLY for type checking
if TYPE_CHECKING:
    import lxml.etree as et

    from assetextractor.parsing.core.assets import AssetCache
    from assetextractor.parsing.core.common import NamedElement
    from assetextractor.parsing.core.texts import Text


class Effect(Asset):
    """Specialized Asset for Patron (Deities) with pre-computed data."""

    def __init__(self, node: et._Element, cache: AssetCache):
        super().__init__(node, cache)

    def _get_text_from_node(self, elm: NamedElement[Any], path: str, fallback: str) -> str:
        """Helper to resolve a Text node path into a localized string."""
        node = elm.find(path)

        if node is not None:
            lang = self.cache.texts.converter.language
            text_attr: Text | None = node()
            if text_attr is not None:
                # Return the localized string, fallback to English, then to the provided default
                return text_attr.get(lang) or text_attr.get("english") or fallback  # type: ignore

        return fallback

    @cached_property
    def buffs(self) -> List[Asset]:
        """Return a list of Assets that can be either 'BuildingBuff', 'ShipBuff' and so on."""
        allowed_template_names = {"BuildingBuff", "ShipBuff"}
        raw_buffs_list = self.find("Effect.Buffs")

        # Define the output buff list.
        # TODO: Explicity provide the correct template classes here (BuildingBuff, ShipBuff, etc).
        out_buffs: List[Asset] = []

        if isinstance(raw_buffs_list, ListAttribute):
            # print(f"This Effect has {len(raw_buffs_list)} buffs.")
            for buff_entry in raw_buffs_list:
                # Get the referenced buff asset
                buff_ref = buff_entry.find("GUID")

                buff_asset: Asset | None = None
                if isinstance(buff_ref, ReferenceAttribute):
                    buff_node = self.cache.get(buff_ref.guid)
                    if isinstance(buff_node, Asset):
                        # TODO: Add the class for 'BuildingBuff' instantiation here.
                        buff_asset = buff_node

                if buff_asset and buff_asset.template.name in allowed_template_names:
                    # print(
                    #     f"Processing Template: {buff_asset.template.name} for the buff {buff_asset.name} (GUID: {buff_asset.guid})"
                    # )

                    # Asign the buff asset to the output buff list.
                    out_buffs.append(buff_asset)

        return out_buffs

    @cached_property
    def targets(self) -> List[Asset | AssetPoolNamed]:
        """Return a list of Assets that can be 'AssetPoolNamed', so multiple entities are affected."""
        allowed_template_names = {"AssetPoolNamed"}
        raw_targets_list = self.find("Effect.Targets")

        # Define the output targets list.
        # TODO: Explicity provide the correct template classes here (AssetPoolNamed).
        out_targets: List[Asset | AssetPoolNamed] = []

        if isinstance(raw_targets_list, ListAttribute):
            # print(f"This Effect has {len(raw_buffs_list)} targets.")
            for target_entry in raw_targets_list:
                # Get the referenced target asset
                target_ref = target_entry.find("GUID")

                target_asset: Asset | None = None
                if isinstance(target_ref, ReferenceAttribute):
                    target_node = self.cache.get(target_ref.guid)
                    if isinstance(target_node, Asset):
                        tpl_name = target_node.template.name
                        match tpl_name:
                            case "AssetPoolNamed":
                                target_asset = AssetPoolNamed(target_node.node, self.cache)
                            case _:
                                # Generic asset assignment.
                                target_asset = target_node

                if target_asset and target_asset.template.name in allowed_template_names:
                    # print(
                    #     f"Processing Template: {target_asset.template.name} for the target {target_asset.name} (GUID: {target_asset.guid})"
                    # )

                    # Asign the buff asset to the output buff list.
                    out_targets.append(target_asset)

        return out_targets
