"""
Standalone script to check boost condition extraction.

Run this to quickly verify that all boost conditions are properly extracted
without the generic "Boost condition active" fallback.

Usage:
    python tests/debugging/check_boost_conditions.py
    Or: uv run python tests/debugging/check_boost_conditions.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from assetextractor.extraction.utils import Config
from assetextractor.parsing.core.assets import Asset, AssetCache


def get_english_name(asset: Asset) -> str:
    """Get the English name of an asset from localization."""
    if asset.text is not None and "english" in asset.text.values:
        return asset.text.values["english"]
    try:
        name = asset.find("Standard.Name")()
        return name if name else f"Asset_{asset.guid}"
    except:
        return f"Asset_{asset.guid}"


def extract_boost_condition(item_asset: Asset) -> str:
    """Extract the boost condition from an ItemWithBoost asset."""
    try:
        condition_attr = item_asset.find("ItemWithBoost.BoostCondition.PreConditionList.Condition")
        if not condition_attr:
            return ""

        condition = condition_attr
        if not condition:
            return ""

        # ConditionAlwaysTrue
        try:
            if hasattr(condition, 'ConditionAlwaysTrue'):
                has_other = any(hasattr(condition, ct) for ct in [
                    'ConditionObjectCount', 'ConditionDominantPatron', 'ConditionNeedAttributeCounter',
                    'ConditionPlayerCounter', 'ConditionActiveEmperor', 'ConditionEmperorRelation',
                    'ConditionReligion', 'ConditionMonumentEventsActive', 'ConditionDiplomacyState',
                    'ConditionItemUsed', 'ConditionWarState', 'ConditionInStorage', 'ConditionTradeRouteCount'
                ])
                if not has_other:
                    return "Always active"
        except:
            pass

        # ConditionObjectCount
        try:
            if hasattr(condition, 'ConditionObjectCount'):
                amount = condition.ConditionObjectCount.Amount()
                comparison_op = condition.ConditionObjectCount.ComparisonOp()
                comparison_map = {0: ">=", "AtLeast": ">=", "AtMost": "<=", "LessThan": "<", "GreaterThan": ">", "Equal": "="}
                op_symbol = comparison_map.get(comparison_op, ">=")
                obj_guid = condition.ObjectFilter.ObjectGUID()
                if obj_guid:
                    obj_name = get_english_name(obj_guid)
                    amount_str = str(int(amount)) if amount == int(amount) else str(amount)
                    return f"{obj_name} {op_symbol} {amount_str}"
        except:
            pass

        # ConditionNeedAttributeCounter
        try:
            if hasattr(condition, 'ConditionNeedAttributeCounter'):
                need_type = condition.ConditionNeedAttributeCounter.NeedAttributeType()
                amount = condition.ConditionNeedAttributeCounter.NeedAttributeAmount()

                if need_type and amount:
                    amount_str = str(int(amount)) if amount == int(amount) else str(amount)
                    return f"{need_type} >= {amount_str}"
        except:
            pass

        # ConditionDominantPatron
        try:
            if hasattr(condition, 'ConditionDominantPatron'):
                patron_guid = condition.ConditionDominantPatron.PatronGUID()
                if patron_guid:
                    return f"Patron: {get_english_name(patron_guid)}"
        except:
            pass

        # ConditionReligion
        try:
            if hasattr(condition, 'ConditionReligion'):
                religion_asset = condition.ConditionReligion.ReligionAsset()
                if religion_asset:
                    return f"Patron: {get_english_name(religion_asset)}"
        except:
            pass

        # ConditionPlayerCounter
        try:
            if hasattr(condition, 'ConditionPlayerCounter'):
                player_counter = condition.ConditionPlayerCounter.PlayerCounter()
                comparison_op = condition.ConditionPlayerCounter.ComparisonOp()
                counter_amount = condition.ConditionPlayerCounter.CounterAmount()
                comparison_map = {0: ">=", "AtLeast": ">=", "AtMost": "<=", "LessThan": "<", "GreaterThan": ">", "Equal": "="}
                op_symbol = comparison_map.get(comparison_op, ">=")

                context_building = condition.ConditionPlayerCounter.Context()
                if context_building:
                    building_name = get_english_name(context_building)
                    amount_str = str(int(counter_amount)) if counter_amount == int(counter_amount) else str(counter_amount)
                    return f"{building_name} {op_symbol} {amount_str}"

                if player_counter and player_counter != 0:
                    counter_name = str(player_counter)
                    amount_str = str(int(counter_amount)) if counter_amount == int(counter_amount) else str(counter_amount)
                    return f"{counter_name} {op_symbol} {amount_str}"
        except:
            pass

        # ConditionActiveEmperor
        try:
            if hasattr(condition, 'ConditionActiveEmperor'):
                emperor = condition.ConditionActiveEmperor.EmperorParticipant()
                if emperor:
                    return f"Emperor: {get_english_name(emperor)}"
        except:
            pass

        # ConditionEmperorRelation
        try:
            if hasattr(condition, 'ConditionEmperorRelation'):
                return "Emperor relation required"
        except:
            pass

        # ConditionDiplomacyState
        try:
            if hasattr(condition, 'ConditionDiplomacyState'):
                profile2 = condition.ConditionDiplomacyState.Profile2()
                desired_state = condition.ConditionDiplomacyState.DesiredState()
                if profile2 and desired_state:
                    profile_name = get_english_name(profile2)
                    return f"Diplomacy with {profile_name}: {desired_state}"
        except:
            pass

        # ConditionTradeRouteCount
        try:
            if hasattr(condition, 'ConditionTradeRouteCount'):
                count = condition.ConditionTradeRouteCount.TradeRouteCount()
                count_op = condition.ConditionTradeRouteCount.CountComparisonOp()
                comparison_map = {0: ">=", "AtLeast": ">=", "AtMost": "<=", "LessThan": "<", "GreaterThan": ">", "Equal": "="}
                op_symbol = comparison_map.get(count_op, ">=")
                if count:
                    return f"Trade routes {op_symbol} {int(count)}"
        except:
            pass

        # ConditionItemUsed
        try:
            if hasattr(condition, 'ConditionItemUsed'):
                item_amount = condition.ConditionItemUsed.ItemAmount()
                if item_amount:
                    return f"{int(item_amount)} items equipped"
        except:
            pass

        # ConditionMonumentEventsActive
        try:
            if hasattr(condition, 'ConditionMonumentEventsActive'):
                return "Monument events active"
        except:
            pass

        # ConditionWarState
        try:
            if hasattr(condition, 'ConditionWarState'):
                return "At war"
        except:
            pass

        # ConditionInStorage
        try:
            if hasattr(condition, 'ConditionInStorage'):
                return "Items in storage"
        except:
            pass

        return "Boost condition active"
    except:
        return ""


def main():
    """Main function to check all boost conditions."""
    print("Loading asset cache...")
    config = Config.from_json("config.json")
    assets = AssetCache.load(config)

    print("Checking boost conditions for all ItemWithBoost assets...\n")

    if "ItemWithBoost" not in assets.templates:
        print("ERROR: ItemWithBoost template not found!")
        return 1

    # Count condition types
    condition_counts = {
        "Always active": 0,
        "ObjectCount": 0,
        "NeedAttributeCounter": 0,
        "DominantPatron/Religion": 0,
        "PlayerCounter": 0,
        "ActiveEmperor": 0,
        "TradeRouteCount": 0,
        "Generic (ERROR)": 0,
        "No condition": 0
    }

    generic_items = []
    specific_test_cases = {
        41350: "Health >= 1000",
        41352: "Happiness >= 1000",
        41351: "Prestige >= 10000",
        41355: "Fire Safety >= 1000",
        41353: "Knowledge >= 10000",
        41354: "Belief >= 10000",
        41360: "Money >= 10000",
    }

    total_items = 0
    for item in assets.templates["ItemWithBoost"].assets:
        total_items += 1
        condition = extract_boost_condition(item)

        # Categorize condition
        if not condition:
            condition_counts["No condition"] += 1
        elif condition == "Always active":
            condition_counts["Always active"] += 1
        elif condition == "Boost condition active":
            condition_counts["Generic (ERROR)"] += 1
            item_name = get_english_name(item)
            generic_items.append((item.guid, item_name, condition))
        elif "Patron:" in condition:
            condition_counts["DominantPatron/Religion"] += 1
        elif "Emperor:" in condition:
            condition_counts["ActiveEmperor"] += 1
        elif "Trade routes" in condition:
            condition_counts["TradeRouteCount"] += 1
        elif any(attr in condition for attr in ["Health", "Happiness", "Prestige", "FireSafety", "Knowledge", "Belief", "Money"]):
            condition_counts["NeedAttributeCounter"] += 1
        elif any(op in condition for op in [" >= ", " <= ", " < ", " > ", " = "]):
            # Could be ObjectCount or PlayerCounter
            if any(counter in condition for counter in ["NavalStrength", "ArmyStrength", "PopulationTotal"]):
                condition_counts["PlayerCounter"] += 1
            else:
                condition_counts["ObjectCount"] += 1

    # Check specific test cases
    print("=== Specific Test Cases ===")
    test_passed = True
    for guid, expected in specific_test_cases.items():
        item = assets[guid]
        actual = extract_boost_condition(item)
        item_name = get_english_name(item)

        status = "✓" if actual == expected else "✗"
        print(f"{status} {guid} ({item_name})")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {actual}")

        if actual != expected:
            test_passed = False

    # Print statistics
    print("\n=== Condition Type Statistics ===")
    print(f"Total ItemWithBoost assets: {total_items}")
    for cond_type, count in condition_counts.items():
        percentage = (count / total_items * 100) if total_items > 0 else 0
        print(f"  {cond_type}: {count} ({percentage:.1f}%)")

    # Report generic conditions
    print("\n=== Generic Conditions (ERRORS) ===")
    if generic_items:
        print(f"Found {len(generic_items)} items with generic 'Boost condition active':")
        for guid, name, condition in generic_items[:20]:  # Show first 20
            print(f"  - {guid}: {name}")
            print(f"    Condition: {condition}")
    else:
        print("✓ No items with generic 'Boost condition active' found!")

    # Final result
    print("\n=== Final Result ===")
    if not test_passed:
        print("✗ FAILED: Some specific test cases did not match expected conditions")
        return 1
    elif generic_items:
        print(f"✗ FAILED: {len(generic_items)} items have generic 'Boost condition active'")
        return 1
    else:
        print("✓ PASSED: All boost conditions are properly extracted!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
