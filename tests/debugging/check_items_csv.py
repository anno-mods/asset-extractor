"""
Standalone script to validate the generated items CSV file.

Run this to verify the CSV has correct data, including boost conditions,
sources, and other item properties.

Usage:
    python tests/debugging/check_items_csv.py
    Or: uv run python tests/debugging/check_items_csv.py
    Or: uv run python tests/debugging/check_items_csv.py results/tables/items_v5.csv
"""

import csv
import sys
from pathlib import Path


def find_latest_csv() -> Path | None:
    """Find the latest items CSV file."""
    results_dir = Path("results") / "tables"
    if not results_dir.exists():
        return None

    csv_files = list(results_dir.glob("items_v*.csv"))
    if not csv_files:
        return None

    # Get the latest version
    return max(csv_files, key=lambda p: p.stat().st_mtime)


def validate_csv(csv_path: Path) -> dict:
    """Validate the CSV file and return statistics."""
    print(f"Validating CSV: {csv_path}")
    print(f"File size: {csv_path.stat().st_size:,} bytes\n")

    # Read CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {"error": "CSV file is empty"}

    # Initialize statistics
    stats = {
        "total_items": len(rows),
        "missing_guid": 0,
        "missing_name": 0,
        "items_with_buffs": 0,
        "items_with_targets": 0,
        "items_with_sources": 0,
        "items_with_boost_condition": 0,
        "items_with_boost_buffs": 0,
        "generic_boost_conditions": [],
        "rarity_counts": {},
        "source_type_counts": {
            "Selling": 0,
            "Research": 0,
            "Quest": 0,
            "Drops": 0,
            "Achievement": 0,
            "Festival": 0,
            "Event": 0,
            "Unlock": 0
        },
        "price_stats": {
            "min": None,
            "max": None,
            "avg": None
        }
    }

    # Check specific test cases
    specific_test_cases = {
        "41350": "Health >= 1000",
        "41352": "Happiness >= 1000",
        "41351": "Prestige >= 10000",
        "41355": "Fire Safety >= 1000",
        "41353": "Knowledge >= 10000",
        "41354": "Belief >= 10000",
        "41360": "Money >= 10000",
    }
    stats["test_case_failures"] = []

    # Validate each row
    prices = []

    for row in rows:
        # Check for missing data
        if not row["guid"]:
            stats["missing_guid"] += 1
        if not row["name"]:
            stats["missing_name"] += 1

        # Count items with data
        if row["buffs"]:
            stats["items_with_buffs"] += 1
        if row["targets"]:
            stats["items_with_targets"] += 1
        if row["source"]:
            stats["items_with_sources"] += 1
        if row["boost_condition"]:
            stats["items_with_boost_condition"] += 1
        if row["boost_buffs"]:
            stats["items_with_boost_buffs"] += 1

        # Check for generic boost conditions
        if row["boost_condition"] == "Boost condition active":
            stats["generic_boost_conditions"].append({
                "guid": row["guid"],
                "name": row["name"]
            })

        # Check specific test cases
        if row["guid"] in specific_test_cases:
            expected = specific_test_cases[row["guid"]]
            actual = row["boost_condition"]
            if actual != expected:
                stats["test_case_failures"].append({
                    "guid": row["guid"],
                    "name": row["name"],
                    "expected": expected,
                    "actual": actual
                })

        # Count rarities
        if row["rarity"]:
            rarity = row["rarity"]
            stats["rarity_counts"][rarity] = stats["rarity_counts"].get(rarity, 0) + 1

        # Count source types
        if row["source"]:
            for source_type in stats["source_type_counts"].keys():
                if f"{source_type}:" in row["source"]:
                    stats["source_type_counts"][source_type] += 1

        # Collect prices
        if row["trade_price"]:
            try:
                prices.append(int(row["trade_price"]))
            except ValueError:
                pass

    # Calculate price statistics
    if prices:
        stats["price_stats"]["min"] = min(prices)
        stats["price_stats"]["max"] = max(prices)
        stats["price_stats"]["avg"] = sum(prices) / len(prices)

    return stats


def print_report(stats: dict) -> bool:
    """Print validation report and return True if passed."""
    if "error" in stats:
        print(f"ERROR: {stats['error']}")
        return False

    print("=== CSV Validation Report ===\n")

    # Basic statistics
    print(f"Total items: {stats['total_items']}")
    print(f"Items with buffs: {stats['items_with_buffs']} ({stats['items_with_buffs']/stats['total_items']*100:.1f}%)")
    print(f"Items with targets: {stats['items_with_targets']} ({stats['items_with_targets']/stats['total_items']*100:.1f}%)")
    print(f"Items with sources: {stats['items_with_sources']} ({stats['items_with_sources']/stats['total_items']*100:.1f}%)")
    print(f"Items with boost condition: {stats['items_with_boost_condition']}")
    print(f"Items with boost buffs: {stats['items_with_boost_buffs']}")

    # Errors
    errors_found = False

    if stats["missing_guid"] > 0:
        print(f"\n✗ ERROR: {stats['missing_guid']} items missing GUID")
        errors_found = True

    if stats["missing_name"] > 0:
        print(f"\n✗ ERROR: {stats['missing_name']} items missing name")
        errors_found = True

    # Rarity distribution
    print("\n=== Rarity Distribution ===")
    for rarity, count in sorted(stats["rarity_counts"].items(), key=lambda x: x[1], reverse=True):
        percentage = count / stats['total_items'] * 100
        print(f"  {rarity}: {count} ({percentage:.1f}%)")

    # Source type breakdown
    print("\n=== Source Type Breakdown ===")
    for source_type, count in stats["source_type_counts"].items():
        if count > 0:
            percentage = count / stats['total_items'] * 100
            print(f"  {source_type}: {count} ({percentage:.1f}%)")

    # Source coverage
    coverage = stats['items_with_sources'] / stats['total_items'] * 100
    print(f"\nSource coverage: {coverage:.1f}%")
    if coverage < 80.0:
        print(f"✗ WARNING: Source coverage below 80% (expected >= 80%)")
        errors_found = True
    else:
        print(f"✓ Source coverage acceptable (>= 80%)")

    # Price statistics
    if stats["price_stats"]["min"]:
        print("\n=== Price Statistics ===")
        print(f"  Min: {stats['price_stats']['min']:,}")
        print(f"  Max: {stats['price_stats']['max']:,}")
        print(f"  Avg: {stats['price_stats']['avg']:,.2f}")

    # Generic boost conditions
    print("\n=== Boost Conditions ===")
    if stats["generic_boost_conditions"]:
        print(f"✗ FAILED: {len(stats['generic_boost_conditions'])} items have generic 'Boost condition active':")
        for item in stats["generic_boost_conditions"][:10]:  # Show first 10
            print(f"  - {item['guid']}: {item['name']}")
        errors_found = True
    else:
        print("✓ No items with generic 'Boost condition active'")

    # Test case failures
    print("\n=== Specific Test Cases ===")
    if stats["test_case_failures"]:
        print(f"✗ FAILED: {len(stats['test_case_failures'])} test cases did not match:")
        for failure in stats["test_case_failures"]:
            print(f"  - {failure['guid']} ({failure['name']}):")
            print(f"    Expected: {failure['expected']}")
            print(f"    Actual:   {failure['actual']}")
        errors_found = True
    else:
        print("✓ All specific test cases passed")

    # Final result
    print("\n=== Final Result ===")
    if errors_found:
        print("✗ FAILED: CSV validation failed with errors")
        return False
    else:
        print("✓ PASSED: CSV validation successful!")
        return True


def main():
    """Main function."""
    # Get CSV path
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = find_latest_csv()

    if not csv_path:
        print("ERROR: No items CSV file found")
        print("Usage: python check_items_csv.py [path/to/items.csv]")
        return 1

    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        return 1

    # Validate CSV
    stats = validate_csv(csv_path)

    # Print report
    passed = print_report(stats)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
