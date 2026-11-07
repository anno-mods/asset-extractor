"""Tests for the CityStatus typed model and extractor JSON export."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from assetextractor.conversion.statistics.city_status_extractor import (
    CityStatusEntryJSON,
    CityStatusExtractor,
    CityStatusRegionJSON,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from assetextractor.parsing.typed.economy.city_status import CityStatus


class _FakeCityStatus:
    def __init__(self, guid: int, name: str, region: str, required_population: int = 0):
        self.guid = guid
        self.name = name
        self.region = region
        self.required_population = required_population
        self.text = lambda: name
        self.icon = None
        self.canonical_name = name.lower().replace(" ", "_")

    @property
    def city_status_info(self):
        return type(
            "FakeCityStatusInfo",
            (),
            {
                "guid": self.guid,
                "name": self.name,
                "incident_interval": type(
                    "FakeIncidentInterval",
                    (),
                    {
                        "fire": None,
                        "unrest": None,
                        "disease": None,
                        "inferno": None,
                        "rebellion": None,
                        "plague": None,
                        "tremors": None,
                    },
                )(),
                "attribute_effects_roman": {},
                "attribute_effects_regional": {},
                "attribute_effects_mixed": {},
            },
        )()


def test_city_status_extractor_groups_by_region_and_exports_json():
    statuses = {
        3564: _FakeCityStatus(3564, "City Status Roman 04", "roman", 1000),
        9801: _FakeCityStatus(9801, "City Status Celtic 02", "celtic", 2200),
    }

    extractor = object.__new__(CityStatusExtractor)
    extractor.city_statuses = cast("dict[int, CityStatus]", statuses)
    extractor.required_population_by_guid = {guid: status.required_population for guid, status in statuses.items()}

    payload = extractor.to_json_dict()

    assert set(payload) == {"roman", "celtic", "egyptian"}
    assert payload["roman"]["levels"][0]["guid"] == "3564"
    assert payload["roman"]["levels"][0]["required_population"] == 1000
    assert payload["celtic"]["levels"][0]["guid"] == "9801"
    assert payload["celtic"]["levels"][0]["required_population"] == 2200
    assert payload["egyptian"]["levels"] == []


def test_city_status_extractor_exports_all_regions():
    statuses = {
        3564: _FakeCityStatus(3564, "City Status Roman 04", "roman", 1000),
        9801: _FakeCityStatus(9801, "City Status Celtic 02", "celtic", 2200),
    }

    extractor = object.__new__(CityStatusExtractor)
    extractor.city_statuses = cast("dict[int, CityStatus]", statuses)
    extractor.required_population_by_guid = {guid: status.required_population for guid, status in statuses.items()}

    payload = extractor.to_json_dict(web_base_path="assets", flatten=True)

    assert set(payload.keys()) == {"roman", "celtic", "egyptian"}
    assert payload["roman"]["levels"][0]["name"] == "City Status Roman 04"
    assert "icon_url" in payload["roman"]["levels"][0]


def test_city_status_extractor_saves_each_region_to_its_own_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    level: CityStatusEntryJSON = {
        "guid": "1929",
        "name": "City Status Roman 01",
        "icon_url": "assets/city_status_roman_01.png",
        "required_population": 0,
        "incident_interval": {},
        "attribute_effects_roman": {},
        "attribute_effects_regional": {},
        "attribute_effects_mixed": {},
    }
    payload: dict[str, CityStatusRegionJSON] = {
        "roman": {"region": "roman", "levels": [level]},
        "celtic": {"region": "celtic", "levels": []},
        "egyptian": {"region": "egyptian", "levels": []},
    }
    extractor = object.__new__(CityStatusExtractor)

    def fake_to_json_dict(web_base_path: str | None = None, flatten: bool = True) -> dict[str, CityStatusRegionJSON]:
        return payload

    extractor.to_json_dict = fake_to_json_dict

    extractor.save_to_json(tmp_path / "city-status")

    output_dir = tmp_path / "city-status"
    assert capsys.readouterr().out.splitlines() == [
        f"Successfully exported {region} city statuses to {output_dir / f'city_status_{region}.json'}"
        for region in payload
    ]

    assert sorted(path.name for path in output_dir.iterdir()) == [
        "city_status_celtic.json",
        "city_status_egyptian.json",
        "city_status_roman.json",
    ]
    assert json.loads((tmp_path / "city-status" / "city_status_roman.json").read_text()) == {"roman_01": level}
