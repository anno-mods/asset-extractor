from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, TypedDict

from assetextractor.conversion.statistics.icon_processor import IconProcessor
from assetextractor.parsing.core.texts import StandardTextConverter
from assetextractor.parsing.typed.achievements.achievement_set import AchievementSet

if TYPE_CHECKING:
    from assetextractor.parsing.core.assets import Asset, AssetCache
    from assetextractor.parsing.typed.achievements.achievement import Achievement


# --- Export JSON Types ---


class AchievementJSON(TypedDict):
    """Achievement metadata."""

    guid: str
    name: str  # Standard.Name
    title: str
    description: str
    icon_url: str
    difficulty: str
    points: int


class AchievementSetJSON(TypedDict):
    """Consolidate each set of achievements metadata."""

    guid: str
    reward: str  # Localized OasisId (title)
    name: str  # Standard.Name
    achievements: list[AchievementJSON]


class AchievementExtractor:
    """Main orchestrator for extracting 'Achievement Sets' from Anno 117 assets."""

    DEFAULT_PRINT_WIDTH = 100

    # Mapping for points based on difficulty
    DIFFICULTY_POINTS = {"Bronze": 15, "Silver": 30, "Gold": 50}  # noqa: RUF012

    def __init__(self, assets: AssetCache, language: str = "english") -> None:
        """Initialize the extractor.

        Parameters
        ----------
        assets : AssetCache
            Asset cache containing all game files and strings.
        language : str, optional
            Language for text localization, by default "english".
        """
        self.assets = assets
        self.language = language
        self.texts = assets.texts
        self.achievement_sets: dict[int, AchievementSet] = {}  # Map of GUID -> AchievementSet
        self.print_width = self.DEFAULT_PRINT_WIDTH

    def _prepare_converter(self) -> None:
        """Ensures the shared cache is using this extractor's language configuration."""
        self.assets.texts.converter = StandardTextConverter(self.language)

    def extract_all(self) -> dict[int, AchievementSet]:
        """Extracts all 'AchievementSet' assets, sorted sequentially by GUID.

        Returns
        -------
        dict[int, AchievementSet]
            A dictionary mapping asset GUIDs to their corresponding sorted AchievementSet instances.
        """
        self._prepare_converter()

        template = self.assets.templates.get("AchievementSet")
        if not template:
            self.achievement_sets = {}
            return {}

        # Filter out valid AchievementSet instances immediately
        valid_assets = (a for a in template.assets if isinstance(a, AchievementSet))

        # Sort the assets by their GUID and construct the ordered dictionary cleanly
        self.achievement_sets = {asset.guid: asset for asset in sorted(valid_assets, key=lambda a: a.guid)}

        return self.achievement_sets

    # --- Printing Methods ---

    def print_achievement_sets(self, guid: int | None = None) -> None:
        """Prints details for stored achievement sets directly from the memory dictionary."""
        if not self.achievement_sets:
            print("No achievement sets loaded in memory. Call extract_all() first.")
            return

        if guid is not None:
            if a_set := self.achievement_sets.get(guid):
                self._print_single_achievement_set(a_set)
            else:
                print(f"AchievementSet with GUID {guid} not found.")
        else:
            for a_set in self.achievement_sets.values():
                self._print_single_achievement_set(a_set)

    def _print_single_achievement_set(self, ach_set: AchievementSet) -> None:
        """Prints formatting for a single 'AchievementSet'."""
        print(f"\n{'=' * self.print_width}")
        print(f"ACHIEVEMENT SET: {ach_set.name} (GUID: {ach_set.guid})".center(self.print_width))
        print(f"{'=' * self.print_width}")

        items = ach_set.achievement_set_info.achievements
        print(f"Contains {len(items)} Achievements:")

        for index, item in enumerate(items):
            print(f"\n  [ACHIVEMENT {index}] {item.name} (GUID: {item.guid})")
            self._print_single_achievement(item)

    def _print_single_achievement(self, ach: Achievement) -> None:
        """Prints an individual 'Achievement'."""
        std_name = ach.name
        info = ach.achievement_info
        print(f"      * {info.achievement_title} (GUID: {ach.guid} | {std_name})")
        print(f"        Difficulty: {info.achievement_difficulty}")
        print(f"        Description: {info.achievement_description}")

    # --- Export Methods ---

    def to_json_dict(self, web_base_path: str | None = None, flatten: bool = True) -> Dict[str, AchievementSetJSON]:
        """Processes the achievement sets into a flat JSON-ready dictionary keyed by GUID."""
        self._prepare_converter()

        if not self.achievement_sets:
            self.extract_all()

        export_data: Dict[str, AchievementSetJSON] = {}

        for guid, a_set in self.achievement_sets.items():
            reward_text = a_set.text() if a_set.text else ""

            achievements_json: list[AchievementJSON] = []
            for ach in a_set.achievements:
                ach_icon = IconProcessor.get_icon_package(ach)
                icon_path = IconProcessor.get_final_url(
                    raw_path=ach_icon["path"],
                    canon_name=ach_icon["canon_name"],
                    web_base_path=web_base_path,
                    flatten=flatten,
                    default_name=ach.canonical_name,
                )

                info = ach.achievement_info
                difficulty = info.achievement_difficulty

                achievements_json.append(
                    {
                        "guid": str(ach.guid),
                        "name": ach.name,
                        "title": info.achievement_title,
                        "description": info.achievement_description,
                        "icon_url": icon_path,
                        "difficulty": difficulty,
                        "points": self.DIFFICULTY_POINTS.get(difficulty, 15),
                    }
                )

            export_data[str(guid)] = {
                "guid": str(a_set.guid),
                "reward": reward_text,
                "name": a_set.name,
                "achievements": achievements_json,
            }

        return export_data

    def save_to_json(self, file_path: Path | str, web_base_path: str | None = None, flatten: bool = True) -> None:
        """Helper to write the exported dictionary to a physical file."""
        data = self.to_json_dict(web_base_path=web_base_path, flatten=flatten)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"Successfully exported {len(data)} achievement sets to {file_path}")

    def _collect_unique_achievements(self) -> List[Asset]:
        """Gathers distinct 'Achievement' assets across all achievement sets, deduped by GUID."""
        if not self.achievement_sets:
            self.extract_all()

        standard_assets: List[Asset] = []
        visited_asset: set[int] = set()

        for a_set in self.achievement_sets.values():
            for item in a_set.achievements:
                if item.guid not in visited_asset:
                    standard_assets.append(item)
                    visited_asset.add(item.guid)

        return standard_assets

    def export_all_achievement_assets(
        self,
        output_base: Path | str,
        quality: int = 75,
        resize: tuple[int, int] | None = (128, 128),
        flatten: bool = False,
    ) -> None:
        """Exports all achievement-related icons."""
        output_path = Path(output_base)
        standard_assets = self._collect_unique_achievements()

        print(f"Exporting {len(standard_assets)} achievement icons...")
        IconProcessor.export_icons(
            assets=standard_assets,
            output_base=output_path,
            flatten=flatten,
            quality=quality,
            resize=resize,
            use_canonical_name=True,
        )

    def export_all_assets(
        self,
        output_base: Path | str,
        quality: int = 75,
        resize: tuple[int, int] | None = (128, 128),
        flatten: bool = False,
    ):
        """Iterates through all resolved underlying achievement and exports their icons."""
        output_path = Path(output_base)
        standard_assets = self._collect_unique_achievements()

        print(f"Started exporting {len(standard_assets)} achievement icons...")
        IconProcessor.export_icons(
            assets=standard_assets,
            output_base=output_path,
            flatten=flatten,
            quality=quality,
            resize=resize,
            use_canonical_name=True,
        )
        print(f"Finished exporting {len(standard_assets)} achievement icons...")
