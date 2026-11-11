"""Regression tests: items that previously extracted without a source."""

import pytest

from assetextractor.conversion.statistics.item_extractor import ItemExtractor


@pytest.fixture(scope="module")
def items_by_guid(assets):
    items = ItemExtractor(assets, language="english").extract_all_items()
    return {item["guid"]: item for item in items}


@pytest.mark.parametrize("guid", [166523, 172289])
def test_dlc03_hof_specialists_have_hall_of_fame_source(items_by_guid, guid):
    assert items_by_guid[guid]["source"] == "Hall Of Fame"


@pytest.mark.parametrize("guid", [184794, 157067])
def test_meta_storage_quest_rewards_have_quest_source(items_by_guid, guid):
    assert "Quest" in str(items_by_guid[guid].get("source", ""))


@pytest.mark.parametrize("guid", [157290, 157291, 157294, 157295, 157292, 159270])
def test_hippodrome_racers_have_quest_source(items_by_guid, guid):
    assert "Quest" in str(items_by_guid[guid].get("source", ""))


def test_fake_item_is_excluded(items_by_guid):
    assert 182642 not in items_by_guid
