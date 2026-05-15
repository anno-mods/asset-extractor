"""
Integration tests for boost condition extraction.

Tests that all ItemWithBoost assets have properly extracted boost conditions
without falling back to the generic "Boost condition active" message.
"""

import csv
from pathlib import Path

import pytest

from assetextractor.extraction.utils import Config
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.conversion.statistics.boost_conditions import BoostConditionParser


@pytest.fixture(scope="module")
def assets():
    """Load asset cache once for all tests."""
    config = Config.from_json("config.json")
    return AssetCache.load(config)


@pytest.fixture(scope="module")
def boost_parser(assets):
    """Create boost condition parser once for all tests."""
    return BoostConditionParser(assets, assets.texts)


def extract_boost_condition(item_asset: Asset, assets: AssetCache) -> str:
    """Extract the boost condition from an ItemWithBoost asset.

    This is a wrapper function for backward compatibility with existing tests.
    """
    parser = BoostConditionParser(assets, assets.texts)
    return parser.parse(item_asset)


class TestBoostConditionExtraction:
    """Test boost condition extraction for all ItemWithBoost assets."""

    def test_no_generic_boost_conditions(self, assets):
        """Verify that no items have the generic 'Boost condition active' message."""
        generic_conditions = []

        if "ItemWithBoost" not in assets.templates:
            pytest.skip("ItemWithBoost template not found")

        for item in assets.templates["ItemWithBoost"].assets:
            condition = extract_boost_condition(item, assets)

            # Skip items with no boost condition
            if not condition:
                continue

            # Flag items with generic condition
            if condition == "Boost condition active":
                item_name = item.text.values.get("english", item.name) if item.text else item.name
                generic_conditions.append({
                    "guid": item.guid,
                    "name": item_name,
                    "condition": condition
                })

        # Assert no generic conditions
        if generic_conditions:
            error_msg = f"Found {len(generic_conditions)} items with generic 'Boost condition active':\n"
            for item_info in generic_conditions[:10]:  # Show first 10
                error_msg += f"  - {item_info['name']} (GUID: {item_info['guid']})\n"
            pytest.fail(error_msg)

    def test_specific_need_attribute_conditions(self, assets):
        """Test specific items that should have NeedAttributeCounter conditions."""
        test_cases = [
            (41350, "Health >= 1000"),
            (41352, "Happiness >= 1000"),
            (41351, "Prestige >= 10000"),
            (41355, "Fire Safety >= 1000"),
            (41353, "Knowledge >= 10000"),
            (41354, "Belief >= 10000"),
            (41360, "Money >= 10000"),
        ]

        for guid, expected_condition in test_cases:
            item = assets[guid]
            condition = extract_boost_condition(item, assets)

            assert condition == expected_condition, (
                f"Item {guid} has incorrect condition. "
                f"Expected: '{expected_condition}', Got: '{condition}'"
            )

    def test_player_counter_naval_strength(self, assets):
        """Test NavalStrength player counter condition."""
        # Item with NavalStrength <= 5000 condition
        # Find it by checking all ItemWithBoost
        found = False

        if "ItemWithBoost" in assets.templates:
            for item in assets.templates["ItemWithBoost"].assets:
                condition = extract_boost_condition(item, assets)
                if "NavalStrength" in condition and "<=" in condition:
                    assert "5000" in condition, f"NavalStrength condition should include 5000: {condition}"
                    found = True
                    break

        if not found:
            pytest.skip("No item with NavalStrength condition found")

    def test_all_condition_types_covered(self, assets):
        """Test that all condition types are recognized and extracted."""
        condition_types = {
            "ConditionAlwaysTrue": 0,
            "ConditionObjectCount": 0,
            "ConditionNeedAttributeCounter": 0,
            "ConditionDominantPatron": 0,
            "ConditionReligion": 0,
            "ConditionPlayerCounter": 0,
            "ConditionActiveEmperor": 0,
            "ConditionEmperorRelation": 0,
            "ConditionDiplomacyState": 0,
            "ConditionTradeRouteCount": 0,
            "ConditionItemUsed": 0,
            "ConditionMonumentEventsActive": 0,
            "ConditionWarState": 0,
            "ConditionInStorage": 0,
        }

        unhandled_conditions = []

        if "ItemWithBoost" not in assets.templates:
            pytest.skip("ItemWithBoost template not found")

        for item in assets.templates["ItemWithBoost"].assets:
            try:
                condition_attr = item.find("ItemWithBoost.BoostCondition.PreConditionList.Condition")
                if not condition_attr:
                    continue

                condition = condition_attr
                if not condition:
                    continue

                # Count condition types
                found_type = False
                for cond_type in condition_types.keys():
                    if hasattr(condition, cond_type):
                        condition_types[cond_type] += 1
                        found_type = True

                # Check for unhandled conditions
                extracted = extract_boost_condition(item, assets)
                if extracted == "Boost condition active":
                    item_name = item.text.values.get("english", item.name) if item.text else item.name
                    unhandled_conditions.append({
                        "guid": item.guid,
                        "name": item_name
                    })
            except:
                pass

        # Print statistics
        print("\n=== Condition Type Statistics ===")
        for cond_type, count in condition_types.items():
            if count > 0:
                print(f"{cond_type}: {count} items")

        # Assert no unhandled conditions
        if unhandled_conditions:
            error_msg = f"Found {len(unhandled_conditions)} items with unhandled conditions:\n"
            for item_info in unhandled_conditions[:10]:
                error_msg += f"  - {item_info['name']} (GUID: {item_info['guid']})\n"
            pytest.fail(error_msg)


class TestItemCSVEndToEnd:
    """End-to-end tests for the generated items CSV file."""

    @pytest.fixture(scope="class")
    def csv_path(self):
        """Get the path to the latest items CSV file."""
        results_dir = Path("results") / "tables"
        csv_files = list(results_dir.glob("items_v*.csv"))

        if not csv_files:
            pytest.skip("No items CSV files found")

        # Get the latest version
        latest_csv = max(csv_files, key=lambda p: p.stat().st_mtime)
        return latest_csv

    @pytest.fixture(scope="class")
    def csv_data(self, csv_path):
        """Load CSV data."""
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def test_csv_file_exists(self, csv_path):
        """Test that the CSV file exists and is readable."""
        assert csv_path.exists(), f"CSV file not found: {csv_path}"
        assert csv_path.stat().st_size > 0, "CSV file is empty"

    def test_csv_has_expected_columns(self, csv_data):
        """Test that CSV has all expected columns."""
        expected_columns = [
            "guid", "name", "rarity", "trade_price", "targets",
            "buffs", "boost_condition", "boost_buffs", "source"
        ]

        if not csv_data:
            pytest.skip("CSV file is empty")

        actual_columns = list(csv_data[0].keys())

        for col in expected_columns:
            assert col in actual_columns, f"Missing column: {col}"

    def test_csv_all_items_have_guid_and_name(self, csv_data):
        """Test that all items have GUID and name."""
        missing_data = []

        for row in csv_data:
            if not row["guid"] or not row["name"]:
                missing_data.append({
                    "guid": row.get("guid", "MISSING"),
                    "name": row.get("name", "MISSING")
                })

        assert not missing_data, f"Found {len(missing_data)} items with missing GUID or name"

    def test_csv_no_generic_boost_conditions(self, csv_data):
        """Test that no items in CSV have generic 'Boost condition active'."""
        generic_conditions = []

        for row in csv_data:
            if row["boost_condition"] == "Boost condition active":
                generic_conditions.append({
                    "guid": row["guid"],
                    "name": row["name"],
                    "condition": row["boost_condition"]
                })

        if generic_conditions:
            error_msg = f"Found {len(generic_conditions)} items in CSV with generic boost condition:\n"
            for item_info in generic_conditions[:10]:
                error_msg += f"  - {item_info['name']} (GUID: {item_info['guid']})\n"
            pytest.fail(error_msg)

    def test_csv_specific_boost_conditions(self, csv_data):
        """Test specific boost conditions in the CSV."""
        test_cases = {
            "41350": "Health >= 1000",
            "41352": "Happiness >= 1000",
            "41351": "Prestige >= 10000",
            "41355": "Fire Safety >= 1000",
            "41353": "Knowledge >= 10000",
            "41354": "Belief >= 10000",
            "41360": "Money >= 10000",
        }

        # Create GUID to row mapping
        guid_to_row = {row["guid"]: row for row in csv_data}

        errors = []
        for guid, expected_condition in test_cases.items():
            if guid in guid_to_row:
                actual_condition = guid_to_row[guid]["boost_condition"]
                if actual_condition != expected_condition:
                    errors.append(
                        f"Item {guid} ({guid_to_row[guid]['name']}): "
                        f"Expected '{expected_condition}', Got '{actual_condition}'"
                    )
            else:
                errors.append(f"Item {guid} not found in CSV")

        if errors:
            pytest.fail("\n".join(errors))

    def test_csv_items_have_sources(self, csv_data):
        """Test that most items have at least one source."""
        items_without_sources = []

        for row in csv_data:
            if not row["source"]:
                items_without_sources.append({
                    "guid": row["guid"],
                    "name": row["name"]
                })

        total_items = len(csv_data)
        items_with_sources = total_items - len(items_without_sources)
        coverage_percent = (items_with_sources / total_items) * 100

        print(f"\n=== Source Coverage ===")
        print(f"Items with sources: {items_with_sources}/{total_items} ({coverage_percent:.1f}%)")
        print(f"Items without sources: {len(items_without_sources)}")

        # Should have at least 80% coverage
        assert coverage_percent >= 80.0, (
            f"Source coverage too low: {coverage_percent:.1f}%. "
            f"Expected at least 80%."
        )

    def test_csv_source_types(self, csv_data):
        """Test that various source types are present in the CSV."""
        source_type_counts = {
            "Selling": 0,
            "Research": 0,
            "Quest": 0,
            "Drops": 0,
            "Achievement": 0,
            "Festival": 0,
        }

        for row in csv_data:
            source_str = row["source"]
            if source_str:
                for source_type in source_type_counts.keys():
                    if f"{source_type}:" in source_str:
                        source_type_counts[source_type] += 1

        print("\n=== Source Type Breakdown ===")
        for source_type, count in source_type_counts.items():
            print(f"{source_type}: {count} items")

        # Should have at least some of each major type
        assert source_type_counts["Selling"] > 0, "No items from Selling sources"
        assert source_type_counts["Research"] > 0, "No items from Research sources"

    def test_csv_item_rarities(self, csv_data):
        """Test that items have valid rarity values."""
        valid_rarities = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Unique", "Quest", "Artifact", "CollectorsEdition"]

        rarity_counts = {}
        invalid_rarities = []

        for row in csv_data:
            rarity = row["rarity"]
            if rarity:
                if rarity in valid_rarities:
                    rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
                else:
                    invalid_rarities.append({
                        "guid": row["guid"],
                        "name": row["name"],
                        "rarity": rarity
                    })

        print("\n=== Rarity Distribution ===")
        for rarity, count in sorted(rarity_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"{rarity}: {count} items")

        if invalid_rarities:
            error_msg = f"Found {len(invalid_rarities)} items with invalid rarity:\n"
            for item_info in invalid_rarities[:10]:
                error_msg += f"  - {item_info['name']} (GUID: {item_info['guid']}): {item_info['rarity']}\n"
            pytest.fail(error_msg)

    def test_csv_items_with_boost_have_condition(self, csv_data, assets):
        """Test that all items with boost buffs have a boost condition."""
        missing_conditions = []

        for row in csv_data:
            # If item has boost_buffs, it should have a boost_condition
            if row["boost_buffs"] and not row["boost_condition"]:
                missing_conditions.append({
                    "guid": row["guid"],
                    "name": row["name"]
                })

        if missing_conditions:
            error_msg = f"Found {len(missing_conditions)} items with boost_buffs but no boost_condition:\n"
            for item_info in missing_conditions[:10]:
                error_msg += f"  - {item_info['name']} (GUID: {item_info['guid']})\n"
            pytest.fail(error_msg)


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
