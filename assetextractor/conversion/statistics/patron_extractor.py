import json
from pathlib import Path
from typing import Dict, List, Sequence, TypedDict

from assetextractor.parsing.typed.asset_pool_base import AssetPoolBase
from assetextractor.parsing.typed.cost import AssetWithCosts
from assetextractor.parsing.typed.maintenance import AssetWithMaintenance
from assetextractor.parsing.typed.patron import Patron
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.texts import StandardTextConverter


class PatronItemJSON(TypedDict):
    """Patron output JSON structure."""

    uid: int
    name: str  # Standard.Name
    title: str  # English by default
    description: str  # English by default
    """In-game description."""
    image_url: str


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

    def _prepare_converter(self):
        """Ensures the shared cache is using this extractor's language."""
        self.assets.texts.converter = StandardTextConverter(self.language)

    def _process_buffs(self, buffs: List[Asset]):
        """Private method to process and print buff assets."""
        print(f"{'-' * 50}")
        print(f"Buffs: {len(buffs)}")

        for buff_index, buff_asset in enumerate(buffs, 1):
            print(f"  |- {buff_index} Buff - {buff_asset.name} (GUID: {buff_asset.guid})")
            match buff_asset:
                case _:
                    # Default generic asset. Do nothing in the meantime.
                    pass

    def _process_targets(self, targets: Sequence[Asset], level: int = 0):
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
                self._process_targets(target_asset.asset_pool_list, level + 1)
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

    def extract_all(self):
        """
        Extract all patron assets using the helper asset factories. Right now
        it only prints.
        """
        self._prepare_converter()

        template = self.assets.templates.get("Patron")
        patrons = [a for a in template.assets if isinstance(a, Patron)] if template else []

        for patron in patrons[:1]:  # Try with Mars only
            print(f"\n{'=' * 50}")
            print(f"PATRON: {patron.name} (GUID: {patron.guid})")
            print(f"{'=' * 50}")

            for eff_index, effect_data in enumerate(patron.local_effects):
                print(f"Title:       {effect_data.title}")
                print(f"Description: {effect_data.description}")

                if effect_data.asset:
                    print(f"Asset GUID:  {effect_data.asset.guid}")

                    # Process Buffs and Targets using private methods
                    self._process_buffs(effect_data.asset.buffs)
                    self._process_targets(effect_data.asset.targets)

                # Separator.
                print(f"{'-' * 50}")

                # Pretty print the Milestones list using asdict for clean JSON output
                if effect_data.milestones:
                    print("Milestones:  ")
                    for mil_index, mil in enumerate(effect_data.milestones):
                        print(f"  * Milestone {mil_index} - Devotion {mil.devotion} - Buff Scaling {mil.buff_scaling}")
                else:
                    print("Milestones:  None")

                if eff_index < len(patron.local_effects) - 1:
                    print(f"{'-' * 50}")

    def to_json_dict(self) -> Dict[str, PatronItemJSON]:
        """
        Processes the patron map into a flat JSON-ready dictionary
        keyed by patron GUID.
        """
        # Switch the shared cache to THIS extractor's language before processing
        self._prepare_converter()

        # TODO: Finish this.
        export_data: Dict[str, PatronItemJSON] = {}

        return export_data

    def save_to_json(self, file_path: Path | str):
        """Helper to write the exported dictionary to a physical file."""
        data = self.to_json_dict()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"Successfully exported {len(data)} ornaments to {file_path}")
