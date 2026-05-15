import json
from pathlib import Path
from typing import Dict, List, Sequence, TypedDict, cast

from assetextractor.conversion.statistics.icon_processor import IconProcessor
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.texts import StandardTextConverter, Text
from assetextractor.parsing.typed.asset_pool_base import AssetPoolBase
from assetextractor.parsing.typed.cost import AssetWithCosts
from assetextractor.parsing.typed.maintenance import AssetWithMaintenance
from assetextractor.parsing.typed.patron import Patron


class PatronItemJSON(TypedDict):
    """Patron output JSON structure."""

    uid: int
    # name: str  # Standard.Name
    # """Raw Name."""
    canon_name: str
    """Canonical Name. This is unique per asset."""
    title: str  # English by default
    description: str  # English by default
    """In-game description."""
    icon_url: str
    """The original 2D asset icon url."""
    canon_icon_name: str
    """Canonical icon name."""


class PatronExtractor:
    """Main orchestrator for extracting patrons from Anno 117 assets."""

    def __init__(self, assets: AssetCache, language: str = "english"):
        """Initialize the patrons extractor.

        Args:
            assets: Asset cache with loaded assets
            language: Language for text localization (default: "english")
        """
        self.assets = assets
        self.language = language
        self.texts = assets.texts
        self.patrons: Dict[int, Patron] = {}  # Stores results after extract_all()

    def _prepare_converter(self):
        """Ensures the shared cache is using this extractor's language."""
        self.assets.texts.converter = StandardTextConverter(self.language)

    def extract_all(self) -> Dict[int, Patron]:
        """
        Extracts all Patron assets and saves them into self.patrons.

        Returns:
            Dict[int, Patron]: A map of Patron GUID to Patron instance.
        """
        self._prepare_converter()

        template = self.assets.templates.get("Patron")
        if not template:
            self.patrons = {}
            return {}

        # Save to self.patrons and return it
        self.patrons = {a.guid: a for a in template.assets if isinstance(a, Patron)}
        return self.patrons

    # --- Printing Methods ---

    def print_patrons(self, guid: int | None = None):
        """
        Prints details for stored patrons.

        Args:
            guid: If provided, only prints that specific patron.
                  If None, prints all stored patrons.
        """
        if not self.patrons:
            print("No patrons loaded in memory. Call extract_all() first.")
            return

        if guid is not None:
            if patron := self.patrons.get(guid):
                self._print_single_patron(patron)
            else:
                print(f"Patron with GUID {guid} not found in current results.")
        else:
            for patron in self.patrons.values():
                self._print_single_patron(patron)

    def _print_single_patron(self, patron: Patron):
        """Internal helper to print the full details of one patron."""
        print(f"\n{'=' * 60}")
        print(f"PATRON: {patron.name} (GUID: {patron.guid})")
        print(f"{'=' * 60}")

        for eff_index, effect_data in enumerate(patron.local_effects):
            print(f"Title:       {effect_data.title}")
            print(f"Description: {effect_data.description}")

            if effect_data.asset:
                print(f"Asset GUID:  {effect_data.asset.guid}")
                self._print_buffs(effect_data.asset.buffs)
                self._print_targets(effect_data.asset.targets)

            print(f"{'-' * 60}")

            if effect_data.milestones:
                print("Milestones:  ")
                for mil_index, mil in enumerate(effect_data.milestones):
                    print(f"  * Milestone {mil_index} - Devotion {mil.devotion} - Buff Scaling {mil.buff_scaling}")
            else:
                print("Milestones:  None")

            if eff_index < len(patron.local_effects) - 1:
                print(f"{'-' * 60}")

    def _print_buffs(self, buffs: List[Asset]):
        """Private method to process and print buff assets."""
        print(f"{'-' * 50}")
        print(f"Buffs: {len(buffs)}")

        for buff_index, buff_asset in enumerate(buffs, 1):
            print(f"  |- {buff_index} Buff - {buff_asset.name} (GUID: {buff_asset.guid})")
            match buff_asset:
                case _:
                    # Default generic asset. Do nothing in the meantime.
                    pass

    def _print_targets(self, targets: Sequence[Asset], level: int = 0):
        """Private method to process and print target assets and asset pools recursively."""
        # Print the header only at the root level
        if level == 0:
            print(f"{'-' * 50}")
            print(f"Targets: {len(targets)}")

        # Calculate indentation based on recursion depth
        indent = "  " * level

        for target_index, target_asset in enumerate(targets, 1):
            # Print the current target with proper indentation
            print(f"{indent}  |- {target_index} Target: {target_asset.name} (GUID: {target_asset.guid})")

            # 1. Handle Recursion First
            if isinstance(target_asset, AssetPoolBase):
                self._print_targets(target_asset.asset_pool_list, level + 1)
                continue  # Move to next target in loop

            # 2. Handle Construction Costs (Common to Buildings and Units)
            if isinstance(target_asset, AssetWithCosts):
                costs = target_asset.formatted_costs
                if costs:
                    cost_str = ", ".join([f"{c.amount} {c.ingredient}" for c in costs])
                    print(f"{indent}     [Costs]: {cost_str}")

            # 3. Handle Maintenance (Specific to Units/Ships)
            if isinstance(target_asset, AssetWithMaintenance):
                m_costs = target_asset.formatted_maintenance_costs
                if m_costs:
                    m_str = ", ".join([f"{m.amount} {m.product}" for m in m_costs])
                    print(f"{indent}     [Maintenance]: {m_str}")

    # --- Export Methods ---

    def to_json_dict(self, web_base_path: str | None = None) -> Dict[str, PatronItemJSON]:
        """
        Processes the patron map into a flat JSON-ready dictionary
        keyed by patron GUID.

        Args:
            web_base_path: The folder prefix used in the final URL.
        """
        # Switch the shared cache to THIS extractor's language before processing
        self._prepare_converter()

        # TODO: Finish this.
        export_data: Dict[str, PatronItemJSON] = {}
        for guid, patron in self.patrons.items():
            # 1. Get the icon package for metadata
            patron_icon = IconProcessor.get_icon_package(patron)

            # 2. Extract localized text
            patron_title = cast("Text | None", patron.find_value("Patron.PatronName"))
            patron_description = cast("Text | None", patron.find_value("Patron.PatronDescription"))

            title = patron_title() if patron_title else "No Title"
            description = patron_description() if patron_description else "No Title"

            # 3. Construct the web-ready icon URL We use the canonical name +
            # .webp extension to match our export or default to the original
            # game path.
            if web_base_path:
                # Custom flattened path (results/icons/patrons/filename.webp)
                canon_icon = patron_icon["canon_name"] or patron.canonical_name
                final_icon_url = f"{web_base_path}/{canon_icon}.webp".replace("\\", "/")
            else:
                # Default to the "original" cleaned game path
                final_icon_url = patron_icon["image_url"] or ""

            export_data[str(guid)] = {
                "uid": patron.guid,
                "canon_name": patron.canonical_name,
                "title": title,
                "description": description,
                "icon_url": final_icon_url,
                "canon_icon_name": patron_icon["canon_name"] or "",
            }
        return export_data

    def save_to_json(self, file_path: Path | str, web_base_path: str | None = None):
        """
        Helper to write the exported dictionary to a physical file.

        Args:
            file_path: Where to save the actual .json file.
            web_base_path: The URL prefix to use for images inside the JSON.
        """
        data = self.to_json_dict(web_base_path=web_base_path)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"Successfully exported {len(data)} ornaments to {file_path}")
