import json
from pathlib import Path
from typing import Dict, List, TypedDict

from assetextractor.conversion.statistics.icon_processor import IconProcessor
from assetextractor.parsing.typed.construction_category import ConstructionCategory
from assetextractor.parsing.typed.ornamental_building import OrnamentalBuilding
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.texts import StandardTextConverter


class ConstructionGroupJSON(TypedDict):
    """Metadata for the construction category."""

    guid: str
    name: str  # From Standard.Name
    localized_name: str  # From Text.OasisId (localized)


class OrnamentItemJSON(TypedDict):
    """Ornament output JSON structure."""

    uid: int
    name: str  # Standard.Name
    title: str  # English by default
    description: str  # English by default
    """In-game description."""
    image_url: str
    """Icon path to the game assets."""
    prestige: int
    """Prestige points granted by building this ornament."""
    cost: int
    """Denarii value."""
    construction_group: ConstructionGroupJSON
    """The immediate parent construction group this ornament belongs to."""
    top_level_group: ConstructionGroupJSON
    """The root construction group of the construction group."""


class OrnamentsExtractor:
    """Main orchestrator for extracting ornaments from Anno 117 assets."""

    def __init__(self, assets: AssetCache, language: str = "english"):
        """Initialize the ornaments extractor.

        Args:
            assets: Asset cache with loaded assets
            language: Language for text localization (default: "english")
        """
        self.assets = assets
        self.language = language

        # Updated map to store: { TopGUID: (TopMetadata, [(Ornament, SubGroupMetadata)]) }
        self.category_map: Dict[
            str, tuple[ConstructionGroupJSON, List[tuple[OrnamentalBuilding, ConstructionGroupJSON]]]
        ] = {}

    def _prepare_converter(self):
        """Ensures the shared cache is using this extractor's language."""
        self.assets.texts.converter = StandardTextConverter(self.language)

    def _map_construction_categories(self):
        """
        Traverses ConstructionCategories recursively to find and group
        all OrnamentalBuildings under their respective parent groups.
        """
        template = self.assets.templates.get("ConstructionCategory")
        categories = [a for a in template.assets if isinstance(a, ConstructionCategory)] if template else []

        for category in categories:
            # We will store pairs: (The Asset, The specific group it was found in)
            ornaments_with_info: List[tuple[OrnamentalBuilding, ConstructionGroupJSON]] = []

            top_group_info: ConstructionGroupJSON = {
                "guid": str(category.guid),
                "name": category.name,
                "localized_name": category.localized_title,
            }

            # 2. Process the buildings inside this category
            # We use a helper to handle the recursive nesting (Categories inside Categories).
            # Start recursion, passing the top-level info as the first 'current_group'
            self._collect_ornaments_recursive(category.building_assets, ornaments_with_info, top_group_info)

            if ornaments_with_info:
                self.category_map[str(category.guid)] = (top_group_info, ornaments_with_info)

    def _collect_ornaments_recursive(
        self,
        assets: List[Asset],
        collection: List[tuple[OrnamentalBuilding, ConstructionGroupJSON]],
        current_group: ConstructionGroupJSON,
    ):
        """Walks the tree, supporting multiple templates and capturing sub-groups."""
        for asset in assets:
            if isinstance(asset, OrnamentalBuilding):
                collection.append((asset, current_group))
            elif isinstance(asset, ConstructionCategory):
                sub_group_info: ConstructionGroupJSON = {
                    "guid": str(asset.guid),
                    "name": asset.name,
                    "localized_name": asset.localized_title,
                }
                self._collect_ornaments_recursive(asset.building_assets, collection, sub_group_info)

    def extract_all(self):
        """
        Extract all ornament-like assets using the nested category mapping.
        Handles both OrnamentalBuilding and PolygonObject.
        """
        # 1. Ensure the mapping is built
        self._map_construction_categories()

        # 2. Iterate through the Top-Level Groups
        # The map stores: { TopGUID: (TopMetadata, [(Ornament, SubGroupMetadata)]) }
        for top_guid, (top_info, items) in self.category_map.items():
            print(f"\n========================================")  # noqa: F541
            print(f"TAB: {top_info['localized_name']} (GUID: {top_guid})")
            print(f"========================================")  # noqa: F541

            for ornament, sub_info in items:
                # Indicate if the item is in a sub-menu
                group_prefix = f"[{sub_info['localized_name']}]" if sub_info["guid"] != top_guid else ""

                print(f"  ---- {group_prefix} {ornament.name} (GUID: {ornament.guid})")

                # Handle localized strings
                print(f"       Title: {ornament.localized_title}")

                # Safely access properties (PolygonObjects will return 0/[])
                if ornament.costs:
                    print(f"       Cost: {int(ornament.costs[0])} denarii")
                else:
                    print(f"       Cost: 0 denarii")  # noqa: F541

                if ornament.prestige > 0:
                    print(f"       Prestige: {ornament.prestige}")

    def to_json_dict(self) -> Dict[str, OrnamentItemJSON]:
        """
        Processes the category map into a flat JSON-ready dictionary
        keyed by ornament GUID.
        """
        # Switch the shared cache to THIS extractor's language before processing
        self._prepare_converter()

        # Ensure the internal map is built
        if not self.category_map:
            self._map_construction_categories()

        export_data: Dict[str, OrnamentItemJSON] = {}
        processed_guids: set[int] = set()  # Tracking set for de-duplication

        for top_guid, (top_info, items) in self.category_map.items():  # type: ignore
            for ornament, sub_info in items:
                # SKIP if we have already exported this building
                if ornament.guid in processed_guids:
                    continue

                processed_guids.add(ornament.guid)

                # Icon processing
                icon_package = IconProcessor.get_icon_package(ornament)

                # Using pre-computed costs from OrnamentalBuilding class
                cost_value = ornament.costs[0] if ornament.costs else 0

                # Build the OrnamentItemJSON structure
                guid_key = str(ornament.guid)
                json_item: OrnamentItemJSON = {
                    "uid": ornament.guid,
                    "name": ornament.name,
                    "title": ornament.localized_title,
                    "description": ornament.localized_description,
                    "image_url": icon_package["image_url"] or "",
                    "prestige": ornament.prestige,
                    "cost": int(cost_value),
                    "construction_group": sub_info,  # Immediate Parent (e.g., 'Benches')
                    "top_level_group": top_info,  # Root Parent (e.g., 'Classic')
                }
                export_data[guid_key] = json_item

        return export_data

    def save_to_json(self, file_path: Path | str):
        """Helper to write the exported dictionary to a physical file."""
        data = self.to_json_dict()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"Successfully exported {len(data)} ornaments to {file_path}")
