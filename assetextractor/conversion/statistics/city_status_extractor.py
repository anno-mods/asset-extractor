from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, TypedDict

from assetextractor.conversion.statistics.icon_processor import IconProcessor
from assetextractor.parsing.core.texts import StandardTextConverter
from assetextractor.parsing.typed.common.enums import Region
from assetextractor.parsing.typed.economy.economy_feature import EconomyFeature

if TYPE_CHECKING:
    from datetime import timedelta

    from assetextractor.parsing.core.assets import Asset, AssetCache
    from assetextractor.parsing.typed.economy.city_status import CityStatus


class CityStatusEntryJSON(TypedDict):
    """Export representation for one city-status level."""

    guid: str
    name: str
    icon_url: str
    required_population: int
    incident_interval: dict[str, int | None]
    attribute_effects_roman: dict[str, int]
    attribute_effects_regional: dict[str, int]
    attribute_effects_mixed: dict[str, int]


class CityStatusRegionJSON(TypedDict):
    """Export representation for one region's city-status ladder."""

    region: str
    levels: list[CityStatusEntryJSON]


class CityStatusExtractor:
    """Extract city status ladders into website-friendly JSON."""

    DEFAULT_PRINT_WIDTH = 100

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
        self.city_statuses: dict[int, CityStatus] = {}
        self.required_population_by_guid: dict[int, int] = {}

    def _prepare_converter(self) -> None:
        """Ensures the shared cache is using this extractor's language configuration."""
        self.assets.texts.converter = StandardTextConverter(self.language)

    def extract_all(self) -> dict[int, CityStatus]:
        """Extract all CityStatus assets through the single EconomyFeature registry."""
        self._prepare_converter()

        feature_template = self.assets.templates.get("EconomyFeature")
        if not feature_template:
            self.city_statuses = {}
            self.required_population_by_guid = {}
            return {}

        city_statuses: dict[int, CityStatus] = {}
        required_population_by_guid: dict[int, int] = {}

        for economy_feature in feature_template.assets:
            if not isinstance(economy_feature, EconomyFeature):
                continue

            region_map = economy_feature.city_status_feature_info

            for entries in region_map.region.values():
                if not entries:
                    continue

                for entry in entries:
                    city_status = entry.city_status
                    city_statuses[city_status.guid] = city_status
                    required_population_by_guid[city_status.guid] = entry.required_population

        self.city_statuses = dict(sorted(city_statuses.items()))
        self.required_population_by_guid = required_population_by_guid
        return self.city_statuses

    # --- Printing Methods ---

    def print_city_statuses(self, guid: int | None = None) -> None:
        """Prints details for stored city levels directly from the memory dictionary."""
        if not self.city_statuses:
            print("No city levels loaded in memory. Call extract_all() first.")
            return

        if guid is not None:
            if city_status := self.city_statuses.get(guid):
                self._print_one(city_status)
            else:
                print(f"City Level with GUID {guid} not found.")
        else:
            print("--- City Statuses ---")
            for i, val in enumerate(self.city_statuses.values()):
                if i > 0:
                    print()  # Add a clean blank line separator between items when printing all
                self._print_one(val)

    def _print_one(self, item: CityStatus) -> None:
        """Prints an individual 'CityStatus' level with consistent spacing."""
        info = item.city_status_info

        # Define clean, consistent indentation levels
        base_indent = 2
        content_indent = 4
        sub_indent = 6

        print(f"{' ' * base_indent}* {info.name} (GUID: {item.guid})")
        print(f"{' ' * content_indent}Title: {info.title}")
        print(f"{' ' * content_indent}Region: {info.region}")
        print(f"{' ' * content_indent}Required Population: {self.required_population_by_guid.get(item.guid, 0)}")
        print(f"{' ' * content_indent}Incident Interval:")

        for inc_name, inc_fv in info.incident_interval.iter_typed_fields():
            print(f"{' ' * sub_indent}- {inc_name}: {inc_fv}")

    # --- Export Methods ---

    def _serialize_level(self, asset: CityStatus, icon_path: str) -> CityStatusEntryJSON:
        """Serialize a CityStatus asset to the JSON payload.

        Required population comes from the EconomyFeature registry rather than the asset itself,
        because that is the canonical source of the level mapping.
        """
        info = asset.city_status_info
        guid = info.guid
        name = info.name
        incident_interval = info.incident_interval
        level_population = self.required_population_by_guid.get(asset.guid, 0)

        def _seconds_or_zero(value: timedelta | None) -> int:
            if value is None:
                return 0
            total_seconds = value.total_seconds()
            return int(total_seconds)

        incident_payload: dict[str, int | None] = {
            "fire": _seconds_or_zero(incident_interval.fire),
            "unrest": _seconds_or_zero(incident_interval.unrest),
            "disease": _seconds_or_zero(incident_interval.disease),
            "inferno": _seconds_or_zero(incident_interval.inferno),
            "rebellion": _seconds_or_zero(incident_interval.rebellion),
            "plague": _seconds_or_zero(incident_interval.plague),
            "tremors": _seconds_or_zero(incident_interval.tremors),
        }

        return {
            "guid": str(guid),
            "name": name,
            "icon_url": icon_path,
            "required_population": level_population,
            "incident_interval": incident_payload,
            "attribute_effects_roman": info.attribute_effects_roman,
            "attribute_effects_regional": info.attribute_effects_regional,
            "attribute_effects_mixed": info.attribute_effects_mixed,
        }

    def to_json_dict(self, web_base_path: str | None = None, flatten: bool = True) -> Dict[str, CityStatusRegionJSON]:
        if not self.city_statuses:
            self.extract_all()

        self.required_population_by_guid = self.required_population_by_guid or {}

        grouped: Dict[str, list[CityStatus]] = {"roman": [], "celtic": [], "egyptian": []}

        for city_status in self.city_statuses.values():
            status_region = str(getattr(city_status, "region", Region.ROMAN)).lower()
            if status_region not in grouped:
                grouped[status_region] = []

            grouped[status_region].append(city_status)

        export_data: Dict[str, CityStatusRegionJSON] = {}
        for key in sorted(grouped):
            levels = sorted(grouped[key], key=lambda entry: int(entry.guid))

            out_levels: List[CityStatusEntryJSON] = []
            for lvl in levels:
                icon = IconProcessor.get_icon_package(lvl)
                icon_path = IconProcessor.get_final_url(
                    raw_path=icon["path"],
                    canon_name=icon["canon_name"],
                    web_base_path=web_base_path,
                    flatten=flatten,
                    default_name=lvl.canonical_name,
                )

                out_levels.append(self._serialize_level(lvl, icon_path))

            export_data[key] = {"region": key, "levels": out_levels}

        return export_data

    def save_to_json(self, output_dir: Path | str, web_base_path: str | None = None, flatten: bool = True) -> None:
        """Save each region's city-status ladder to its own JSON file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for region, payload in self.to_json_dict(web_base_path=web_base_path, flatten=flatten).items():
            file_path = output_dir / f"city_status_{region}.json"
            levels_by_name = {"_".join(level["name"].split()[-2:]).lower(): level for level in payload["levels"]}
            with file_path.open("w", encoding="utf-8") as handle:
                json.dump(levels_by_name, handle, indent=4, ensure_ascii=False)
            print(f"Successfully exported {region} city statuses to {file_path}")

    def _collect_unique_assets(self) -> List[Asset]:
        """Gathers distinct assets across all city levels, deduped by GUID."""
        if not self.city_statuses:
            self.extract_all()

        standard_assets: List[Asset] = []
        visited_asset: set[int] = set()

        for item in self.city_statuses.values():
            if item.guid not in visited_asset:
                standard_assets.append(item)
                visited_asset.add(item.guid)

        return standard_assets

    def export_all_assets(
        self,
        output_base: Path | str,
        quality: int = 75,
        resize: tuple[int, int] | None = (128, 128),
        flatten: bool = False,
    ):
        """Iterates through all resolved underlying city levels and exports their icons."""
        output_path = Path(output_base)
        standard_assets = self._collect_unique_assets()

        print(f"Started exporting {len(standard_assets)} city level icons...")
        IconProcessor.export_icons(
            assets=standard_assets,
            output_base=output_path,
            flatten=flatten,
            quality=quality,
            resize=resize,
            use_canonical_name=True,
        )
        print(f"Finished exporting {len(standard_assets)} city level icons...")
