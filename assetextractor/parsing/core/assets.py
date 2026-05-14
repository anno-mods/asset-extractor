from __future__ import annotations

import re
import typing as t
from contextlib import suppress

import lxml.etree as et

from assetextractor.parsing.core.attributes import (
    DictAttribute,
    FileNameAttribute,
    ListAttribute,
    Property,
    ReferenceAttribute,
    TemplateAttribute,
    TextAttribute,
)
from assetextractor.parsing.core.common import ElementCache, Group, NamedElement, WeightedReference
from assetextractor.parsing.core.properties import Attribute, DatasetCache, MetaPropertyCache
from assetextractor.parsing.core.templates import NamedRefColT, Template, TemplateCache, TemplateGroup
from assetextractor.parsing.core.texts import TextCache
from assetextractor.parsing.core.uitext import BuffUI, UITextCache

if t.TYPE_CHECKING:
    from pathlib import Path

    from assetextractor.extraction.utils import Config


class Asset(NamedElement["AssetCache"]):
    IGNORED_TAGS = ("Template", "BaseAssetGUID")
    _registry: t.ClassVar[dict[str, type[Asset]]] = {}

    def __init_subclass__(cls, template_names: list[str] | str | None = None, **kwargs: t.Any) -> None:
        super().__init_subclass__(**kwargs)
        if template_names is not None:
            for name in ([template_names] if isinstance(template_names, str) else template_names):
                Asset._registry[name] = cls

    @classmethod
    def create(cls, node: et._Element, cache: AssetCache) -> Asset:
        """Instantiate the registered subclass for this node's Template, or Asset."""
        template_name = node.findtext("Template")
        subclass = cls._registry.get(template_name, cls) if template_name else cls
        return subclass(node, cache)

    def __init__(self, node: et._Element, cache: AssetCache):
        super().__init__(node, None, cache, name="")

        self.cache = cache

        guid_text = node.findtext("Values/Standard/GUID")
        if guid_text is None:
            raise ValueError(f"GUID missing in {node.text}.")
        self.guid = int(guid_text)

        self.name: str = node.findtext("Values/Standard/Name") or ""

        self.text = None
        if text_id := node.findtext("Values/Text/OasisId"):
            with suppress(Exception):
                self.text = cache.texts.get(int(text_id))
        if self.text is None:
            self.text = cache.texts.get(self.guid)

        self.base_asset_guid = self.get_value("BaseAssetGUID", int)
        self.base_asset = None
        self.instances: dict[int, WeightedReference] = dict()

        template_name = self.get_value("Template")
        if template_name is None and self.base_asset_guid is None:
            raise ValueError(f"Template missing in Asset {self.name}.")

        self.referenced_by: dict[int, WeightedReference] = dict()

        self.unlocked_by_dlcs: dict[int, WeightedReference] = dict()
        self.dlc_unlocks: dict[int, WeightedReference] = dict()
        self.in_reward_pool: dict[int, WeightedReference] = dict()
        self.in_asset_pool: dict[int, WeightedReference] = dict()
        self.named_reference_collections: NamedRefColT = {
            "Instances": self.instances,
            "Referenced by": self.referenced_by,
            "Unlocked by DLCs": self.unlocked_by_dlcs,
            "DLC Unlocks": self.dlc_unlocks,
            "In Reward Pools": self.in_reward_pool,
            "In Asset Pools": self.in_asset_pool,
        }  # Referenced by, construction cost, etc.

        self.properties: dict[str, Property] = dict()

        self.value_node = node.find("Values")
        if self.value_node is None:
            self.value_node = self.node

        if template_name is None:
            return  # properties filled in resolve_inheritance

        template = self.cache.templates[template_name]

        if template is None:
            raise ValueError(f"Template {template_name} not found for asset {self.guid}.")

        self.template = template
        self.template.add_instance(self)

        for template_property in self.template.properties.values():
            self._process_property(template_property)

        self._update_text()

    @property
    def identifier(self):
        return str(self.guid)

    @property
    def property_path(self) -> str:
        return ""

    def _process_property(self, template_property: Property):
        assert self.value_node is not None
        name = template_property.name
        child = self.value_node.find(name)

        if child is None or len(child) == 0:
            property = template_property
        else:
            property = Property(child, self, template_property.meta, self.cache.properties)
            property.resolve_inheritance(template_property)

        self.properties[name] = property
        setattr(self, name, property)

    def _update_text(self):
        if self.text is None:
            match = re.match(r"^[A-Z][a-z]*", self.template.name)
            template_word = match.group(0) if match else ""

            for path in [
                f"{self.template.name}.{self.template.name}Name",
                f"{self.template.name}.{template_word}Name",
                "Decision.DecisionScreenConfig.Headline",
            ]:
                text_attr = self.find(path)

                if isinstance(text_attr, TextAttribute) and text_attr() is not None:
                    self.text = text_attr()
                    return

    def resolve_inheritance(self, asset: Asset):
        self.base_asset = asset
        self.template = asset.template
        self.template.add_instance(self)
        asset.instances[self.guid] = WeightedReference(self, asset, "BaseAssetGUID")

        for base_property in asset.properties.values():
            self._process_property(base_property)

        self._update_text()

    def set_referenced_by(self, source: Asset, reference: ReferenceAttribute):
        self.referenced_by[source.guid] = WeightedReference(source, self, reference.property_path)

    def print_tree(self):
        print(str(self))
        for property in self.properties.values():
            property.print_tree("\t")

        print("*) inherited **) default")

    def print_meta_tree(self):
        self.template.print_meta_tree()

    @property
    def short_description(self) -> str:
        if self.text is not None:
            text = self.text()  # use text converter
            if len(text) <= 120:
                return text
            else:
                return text[:120] + "..."

        if self.name:
            return self.name

        return "{" + self.identifier + "}"

    @property
    def long_description(self):
        assert self.template
        return f"{self.name} [{self.guid} - {self.template.name}]"

    @property
    def is_compound(self) -> bool:
        return True

    def find_ref(self, path: str) -> Asset | None:
        """Follow path and return the referenced Asset, or None if missing or unresolved."""
        return t.cast(Asset | None, self.find_value(path))

    @property
    def icon(self) -> FileNameAttribute | None:
        icon = self.find("Standard.IconFilename")
        if isinstance(icon, FileNameAttribute) and icon.is_image:
            return icon
        return None

    @property
    def canonical_name(self) -> str:
        """Generate a canonical, URL-safe name for this asset.

        Format: {template_word}_{cleaned_name}[_{region}]
        - template_word: First word of template name (lowercase)
        - cleaned_name: English name cleaned for URLs
        - region: For production buildings, the associated region

        Examples:
            - "production_resin_tapper_latium" (Production Area with Roman region)
            - "item_dorian" (ItemWithBoost)
        """
        import re

        def clean_name(text: str) -> str:
            """Clean a name to be URL-safe."""
            # Take first part before comma
            text = text.split(",")[0].strip()
            # Convert to lowercase and replace non-alphanumeric with underscores
            text = re.sub(r"[^a-z0-9]+", "_", text.lower())
            # Remove leading/trailing underscores
            text = text.strip("_")
            # Replace multiple underscores with single
            text = re.sub(r"_+", "_", text)
            return text

        def get_region_canonical_name(region_code: str) -> str:
            """Get canonical region name from region code using UITextCache."""
            # Try to get region name from UITextCache
            if self.cache.properties.ui_text_cache is not None:
                ui_mapping = self.cache.properties.ui_text_cache.get_ui_text("Region", region_code)
                if ui_mapping is not None and ui_mapping.text is not None and "english" in ui_mapping.text.values:
                    region_name = ui_mapping.text.values["english"]
                    return clean_name(region_name)

            # Fallback to region code
            return region_code.lower()

        # Get template first word (handle both "Production Area" and "ItemWithBoost")
        if self.template:
            template_name = self.template.name

            if template_name.startswith("SlotFactoryBuilding"):
                template_name = "Production"

            # Try splitting by space first
            if " " in template_name:
                template_word = template_name.split()[0].lower()
            else:
                # Extract first CamelCase word
                match = re.match(r"^[A-Z][a-z]*", template_name)
                template_word = match.group(0).lower() if match else template_name.lower()
        else:
            template_word = "asset"

        # Get English name
        english_name = ""
        text = self.text
        tech = self.find("Tech.TechName")
        if isinstance(tech, TextAttribute):
            text = tech()
        if text and "english" in text.values:
            english_name = text.values["english"]
        elif self.name:
            english_name = self.name

        # Clean the name
        cleaned = clean_name(english_name) if english_name else clean_name(self.name or "None")

        # Build canonical name parts
        parts = [cleaned] if cleaned.startswith(template_word) else [template_word, cleaned]

        # For production buildings, add region
        if template_word == "production":
            try:
                regions_attr = self.find("Building.AssociatedRegions")
                if isinstance(regions_attr, Attribute):
                    region_list = t.cast("t.Optional[list[t.Any]]", regions_attr())
                    if isinstance(region_list, list) and len(region_list) > 0:
                        # Get first region
                        region_code = str(region_list[0])
                        # Get canonical region name
                        region_name = get_region_canonical_name(region_code)
                        parts.append(region_name)
            except (AttributeError, TypeError, ValueError):
                pass

        return "_".join(parts)

    def __getitem__(self, key: str) -> Property | None:
        """Allows bracket notation access to elements."""
        return self.properties.get(key)

    def __iter__(self):
        for property in self.properties.values():
            yield property

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        return key in self.properties

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return self.short_description

    @property
    def buff_ui(self) -> list["BuffUI"]:
        """Get all BuffUI representations from all attributes in this asset.

        This recursively traverses all properties and attributes to collect
        BuffUI objects that represent the asset's effects/buffs.

        Returns:
            List of BuffUI objects from all attributes with buff UI representations
        """
        return self.get_buff_ui()

    def get_buff_ui(self, is_additional_effect: bool = False) -> list["BuffUI"]:
        result: list[BuffUI] = []

        buff_list = self.find("Effect.Buffs")
        if isinstance(buff_list, ListAttribute):
            for buff in buff_list:
                ref = buff.find_ref("GUID")
                if isinstance(ref, Asset):
                    result.extend(ref.get_buff_ui(is_additional_effect))

            return result

        def process_property(prop: Property) -> None:
            """Recursively process a property and its nested content."""
            # Process nested properties
            for nested_prop in prop.properties.values():
                process_property(nested_prop)

            # Process attributes
            for attr in prop.attributes.values():
                process_attribute(attr)

        def process_attribute(attr: Attribute[t.Any, t.Any]) -> None:
            """Process an attribute and collect its BuffUI."""
            buff_ui_list: list[BuffUI] | None = None
            buff_ui_value: BuffUI | None = None

            if isinstance(attr(), Asset) and attr.name == "AdditionalFunctionalEffect" and not is_additional_effect:
                buff_ui_list = attr().get_buff_ui(True)
            elif hasattr(attr, "buff_ui"):
                if isinstance(attr, DictAttribute):
                    buff_ui_list = attr.get_buff_ui(is_additional_effect)
                elif isinstance(attr, ListAttribute):
                    buff_ui_list = attr.buff_ui
                else:
                    val = attr.buff_ui  # pyright: ignore
                    if isinstance(val, BuffUI):
                        buff_ui_value = val

            if buff_ui_value is not None:
                # PrimitiveAttribute, UpgradeAttribute return single BuffUI
                result.append(buff_ui_value)

            if buff_ui_list is not None:
                # ListAttribute, FlagsAttribute, DictAttribute return lists
                result.extend(buff_ui_list)

            # Recursively process compound attributes
            if isinstance(attr, Property):
                process_property(attr)
            elif isinstance(attr, DictAttribute):
                # DictAttribute.buff_ui already handles entries
                pass
            elif isinstance(attr, TemplateAttribute):
                for nested_prop in attr._value_list:
                    process_property(nested_prop)
            elif isinstance(attr, ListAttribute):
                # ListAttribute.buff_ui already handles its items
                pass

        # Start traversal from all top-level properties
        for prop in self.properties.values():
            process_property(prop)

        return result

    def pool_assets(self, cumulative_probability: float = 1.0, visited: set[int] | None = None) -> dict["Asset", float]:
        """Recursively flatten pool tree to get weighted leaf assets with probabilities.

        Args:
            cumulative_probability: Probability accumulated from parent pools (0.0 to 1.0)
            visited: Set of pool GUIDs already visited (cycle detection)

        Returns:
            Dict mapping Asset → probability (cumulative probability of selecting this asset)
        """
        # Initialize tracking
        if visited is None:
            visited = set()

        # Cycle detection
        if self.guid in visited:
            return {}

        visited.add(self.guid)
        result: dict[Asset, float] = {}

        # Check if this asset is a pool
        if "Pool" not in self.template.name:
            return {self: cumulative_probability}

        # Determine pool type and get entries
        entries = None
        is_reward_pool = False

        if "RewardPool" in self.template.name:
            is_reward_pool = True
            with suppress(AttributeError, Exception):
                entries = self.find("RewardPool.ItemsPool")
        elif "AssetPool" in self.template.name:
            with suppress(AttributeError, Exception):
                entries = self.find("AssetPool.AssetList")

        # If no entries found, return empty dict
        if entries is None or not isinstance(entries, ListAttribute) or len(entries) == 0:
            return {}

        # Calculate total weight for normalization
        total_weight = 0.0
        if is_reward_pool:
            for entry in entries:
                try:
                    if entry.find_ref("ItemLink") is not None:
                        weight_attr = entry.find("Weight")
                        if weight_attr is not None:
                            val = weight_attr()
                            weight = val if isinstance(val, int | float) else 1.0
                            total_weight += weight
                except (AttributeError, Exception):
                    pass
        else:  # AssetPool
            for entry in entries:
                try:
                    if entry.find_ref("Asset") is not None:
                        total_weight += 1.0
                except (AttributeError, Exception):
                    pass

        # If total weight is zero, return empty dict
        if total_weight == 0:
            return {}

        # Process each entry
        for entry in entries:
            try:
                # Get referenced asset
                ref_asset = entry.find_ref("ItemLink") if is_reward_pool else entry.find_ref("Asset")

                if ref_asset is None:
                    continue

                # Get weight
                weight = 1.0
                if is_reward_pool:
                    weight_attr = entry.find("Weight")
                    if weight_attr is not None:
                        val = weight_attr()

                        if isinstance(val, int | float):
                            weight = val

                # Calculate local probability
                local_prob = weight / total_weight

                # Calculate new cumulative probability
                new_prob = cumulative_probability * local_prob

                # Recursively call pool_assets
                child_results = ref_asset.pool_assets(new_prob, visited.copy())

                # Merge results with probability accumulation
                for asset, prob in child_results.items():
                    if asset in result:
                        result[asset] += prob  # Accumulate probabilities
                    else:
                        result[asset] = prob

            except (AttributeError, Exception):
                # Skip entries that cause errors
                continue

        return result


class AssetGroup(Group["AssetCache"]):
    """Represents a group in the assets.xml."""

    def __init__(self, node: et._Element, parent: AssetGroup | None, template_group: TemplateGroup, cache: AssetCache):
        super().__init__(node, parent, cache, name=template_group.name)

        self.cache = cache

        for child in self.node.iterchildren():
            if child.tag == "Groups":
                for subchild, template_subgroup in zip(child.iterchildren(), template_group.subgroups.values()):
                    assert template_subgroup is TemplateGroup  # FIXME: Is this correct?
                    group = AssetGroup(subchild, self, template_subgroup, self.cache)
                    self.subgroups[group.name] = group
            elif child.tag == "Assets":
                for subchild in child.iterchildren():
                    asset = Asset.create(subchild, self.cache)
                    self.cache.add(asset)
                    self.elements[asset.guid] = asset
            else:
                raise ValueError(f"Unknown tag: {child.tag} in group {self.full_path}")


class AssetCache(ElementCache[t.Any]):
    def __init__(self, path: Path, templates: TemplateCache):
        super().__init__(path)

        self.templates = templates
        self.properties = templates.properties
        self.texts = self.properties.texts
        self.datasets = self.properties.datasets

        parser = et.XMLParser(huge_tree=True, remove_comments=True)
        if path.is_file():
            self.tree = et.parse(str(path), parser)
        else:
            root = et.Element("Root")
            for file in path.rglob("*.xml"):
                if file.name == "test.xml":
                    continue
                tree = et.parse(str(file), parser)
                if tree.getroot().tag == "Group":
                    root.append(tree.getroot())
                self.tree = et.ElementTree(root)

        # for element, template_group in zip(self.tree.xpath("/AssetList/Groups/Group"), self.templates.groups.values()):
        #     group = AssetGroup(element, self, template_group, self)
        #     self.groups[group.name] = group

        for element in self.tree.xpath("//Assets/Asset"):
            asset = Asset.create(element, self)
            self.elements[asset.guid] = asset

        # Ensure datasets are loaded before resolving references and DLCs
        # because DLC detection needs the Region dataset
        _ = self.datasets.elements

        for asset in self.elements.values():
            self.resolve_inheritance(asset)

        for template in self.templates:
            self.resolve_references(template)

        for asset in self.elements.values():
            self.resolve_references(asset)

        self.resolve_dlc_unlocks()

        # Initialize UI text cache after all assets are loaded
        self._initialize_ui_text_cache()

        # Build pool references after all assets and references are resolved
        try:
            self._build_pool_references()
        except Exception as e:
            import logging

            logger = logging.getLogger("parsing.assets")
            logger.warning(f"Failed to build pool references: {e}")
            # Non-critical, continue without pool references

    def add(self, element: Asset):
        if self.key_type is str:
            super().add(element)
        else:
            self.elements[element.guid] = element

    def resolve_inheritance(self, asset: Asset):
        if asset.base_asset_guid is None or asset.base_asset is not None:
            return

        base_asset = self.elements[asset.base_asset_guid]
        self.resolve_inheritance(base_asset)  # recursively resolve inheritance of base asset first

        cls = Asset._registry.get(base_asset.template.name, Asset)
        if cls is not Asset and type(asset) is Asset:
            typed = cls(asset.node, asset.cache)
            self.elements[typed.guid] = typed
            typed.resolve_inheritance(base_asset)
        else:
            asset.resolve_inheritance(base_asset)

    def resolve_references(self, asset: Asset | Template):
        def process_property(property: Property):
            for meta_property in property.meta.properties.values():
                process_property(getattr(property, meta_property.name))

            for value_definition in property.meta.value_definitions.values():
                attr = getattr(property, value_definition.name)
                if attr is None:
                    print(f"Missing attribute {value_definition.name} in {property.full_path}")
                    pass
                else:
                    process_attribute(attr)

        def process_attribute(element: Attribute[t.Any, t.Any]):
            if isinstance(element, ReferenceAttribute):
                if element.guid == 0:  # Skip references with default value
                    return

                if isinstance(asset, Asset):
                    element.set_reference(asset, self.get(element.guid))

            if isinstance(element, ListAttribute):
                for item in element:
                    for attr in item:
                        if not isinstance(attr, Property):
                            process_attribute(attr)

            if isinstance(element, DictAttribute):
                for attr in element:
                    process_attribute(attr)

            if isinstance(element, TemplateAttribute):
                if isinstance(asset, Asset):
                    element.set_reference(asset)

                if not element._is_initialized:
                    raise ValueError(f"AutoCreateAsset {element.full_path} [{element.source}] not initialized.")

                for attr in element:
                    process_property(attr)

        for property in asset.properties.values():
            process_property(property)

    def resolve_dlc_unlocks(self):
        from assetextractor.parsing.core.dlc_detection import DLCDetector

        DLCDetector(self).detect()

    def _initialize_ui_text_cache(self):
        """Initialize UI text cache after all assets are loaded.

        This must be called after all assets and references are resolved,
        as it needs to access configuration assets to build lookup tables.

        Note: Since assets are already loaded, this will not automatically attach
        UI text to existing PrimitiveAttributes. They will only be attached to
        attributes created after this point (which should be none in normal usage).
        """
        import logging

        logger = logging.getLogger("parsing.assets")
        logger.info("Initializing UI text cache...")

        try:
            ui_cache = UITextCache(self)
            self.properties.ui_text_cache = ui_cache
            logger.info(f"UI text cache initialized with {len(ui_cache)} mappings")
        except Exception as e:
            logger.warning(f"Failed to initialize UI text cache: {e}")
            # Non-critical, continue without UI text cache
            self.properties.ui_text_cache = None

    def _build_pool_references(self):
        """Build reverse pool references for all assets.

        Only includes "root pools" - pools that are directly referenced by non-pool assets.
        Subpools (pools only referenced by other pools) are not tracked separately.
        """
        import logging

        logger = logging.getLogger("parsing.assets")
        logger.info("Building pool references...")

        # Find all pool assets
        pool_assets: list[Asset] = []
        for asset in self.elements.values():
            if "Pool" in asset.template.name:
                pool_assets.append(asset)

        # Identify root pools and flatten them
        root_reward_pools: list[Asset] = []
        root_asset_pools: list[Asset] = []

        for pool in pool_assets:
            # Check if this pool is referenced by any non-pool asset
            is_root_pool = False
            for reference in pool.referenced_by.values():
                if "Pool" not in reference.source.template.name:
                    is_root_pool = True
                    break

            if not is_root_pool:
                continue  # This is a subpool, skip it

            # Determine pool type
            if "RewardPool" in pool.template.name:
                root_reward_pools.append(pool)
            elif "AssetPool" in pool.template.name:
                root_asset_pools.append(pool)

        # Flatten root reward pools
        for pool in root_reward_pools:
            try:
                pool_results = pool.pool_assets()

                # Build WeightedReference objects
                for leaf_asset, probability in pool_results.items():
                    weighted_ref = WeightedReference(source=pool, target=leaf_asset, weight=probability)
                    leaf_asset.in_reward_pool[pool.guid] = weighted_ref
            except Exception as e:
                logger.warning(f"Failed to flatten reward pool {pool.guid} ({pool.name}): {e}")

        # Flatten root asset pools
        for pool in root_asset_pools:
            try:
                pool_results = pool.pool_assets()

                # Build WeightedReference objects
                for leaf_asset, probability in pool_results.items():
                    weighted_ref = WeightedReference(source=pool, target=leaf_asset, weight=probability)
                    leaf_asset.in_asset_pool[pool.guid] = weighted_ref
            except Exception as e:
                logger.warning(f"Failed to flatten asset pool {pool.guid} ({pool.name}): {e}")

        # Log statistics
        leaf_assets_with_reward_pools = sum(1 for asset in self.elements.values() if len(asset.in_reward_pool) > 0)
        leaf_assets_with_asset_pools = sum(1 for asset in self.elements.values() if len(asset.in_asset_pool) > 0)

        logger.info(
            f"Pool references built: {len(root_reward_pools)} root reward pools, "
            f"{len(root_asset_pools)} root asset pools, "
            f"{leaf_assets_with_reward_pools} leaf assets in reward pools, "
            f"{leaf_assets_with_asset_pools} leaf assets in asset pools"
        )

    @staticmethod
    def load(config: Config) -> AssetCache:
        """Loads the asset cache from the given config."""
        import assetextractor.parsing.typed  # noqa: F401

        """Determine paths for 117 or 1800"""
        unpacked_path = config.cache_path
        if (unpacked_path / "data/base").exists():
            export_dir = unpacked_path / "data/base/config/export"
            game_dir = unpacked_path / "data/base/config/game"
            game_asset_dir = game_dir / "asset"

            # ignore old game assets
            # if not game_asset_dir.exists():
            game_asset_dir = None
            gui_dir = unpacked_path / "data/base/config/gui"
        else:
            export_dir = unpacked_path / "data/config/export/main/asset"
            game_dir = None
            game_asset_dir = None
            gui_dir = unpacked_path / "data/config/gui"

        if not export_dir.exists():
            raise FileNotFoundError(f"Directory {export_dir} not found.")

        """Load datasets"""
        dataset_path = export_dir / "datasets.xml"
        if not dataset_path.exists() and game_dir is not None:
            dataset_path = game_dir / "datasets.xml"

        if not dataset_path.exists():
            raise FileNotFoundError(f"File {dataset_path} not found.")

        datasets = DatasetCache(dataset_path)

        """Load texts"""
        language = datasets["Language"]

        if language is None:
            raise ValueError("Language not found in datasets.xml.")

        texts = TextCache(gui_dir, language)

        """Load properties"""
        path_properties = export_dir / "properties-toolone.xml"

        if not path_properties.exists():
            path_properties = export_dir / "properties-meta.xml"

        if not path_properties.exists() and game_asset_dir is not None:
            path_properties = game_asset_dir / "properties.xml"

        if not path_properties.exists():
            raise FileNotFoundError(f"File {path_properties} not found.")

        properties = MetaPropertyCache(path_properties, unpacked_path, datasets, texts)

        """Load templates"""
        path_templates = (
            game_asset_dir / "templates.xml" if game_asset_dir is not None else export_dir / "templates.xml"
        )

        if not path_templates.exists():
            raise FileNotFoundError(f"File {path_templates} not found.")

        templates = TemplateCache(path_templates, properties)

        path_assets = game_asset_dir if game_asset_dir is not None else export_dir / "assets.xml"

        return AssetCache(path_assets, templates)
