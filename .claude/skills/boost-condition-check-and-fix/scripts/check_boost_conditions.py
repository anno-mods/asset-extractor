"""One-shot boost-condition audit for Anno 117 items.

Loads the asset cache ONCE (the slow part, ~30s) and then either:
  - scans every Item/ItemWithBoost asset and lists the ones whose boost
    condition still falls back to the generic "Boost condition active"
    string, dumping each one's raw Condition tree, or
  - (if GUIDs are passed as arguments) dumps just those GUIDs' Condition
    trees, skipping the full scan entirely.

Usage (run from the repo root, or anywhere - the script fixes sys.path):
    uv run python .claude/skills/boost-condition-check-and-fix/scripts/check_boost_conditions.py
    uv run python .claude/skills/boost-condition-check-and-fix/scripts/check_boost_conditions.py 160060 156726
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from assetextractor.conversion.statistics.boost_conditions import BoostConditionParser  # noqa: E402
from assetextractor.extraction.utils import Config  # noqa: E402
from assetextractor.parsing.core.assets import Asset, AssetCache  # noqa: E402

CONDITION_PATH = "ItemWithBoost.BoostCondition.PreConditionList.Condition"
FALLBACK_TEXT = "Boost condition active"


def find_unhandled(assets: AssetCache, parser: BoostConditionParser) -> list[Asset]:
    """Scan Item + ItemWithBoost templates for items still using the fallback text."""
    seen: set[int] = set()
    unhandled: list[Asset] = []
    for template_name in ("Item", "ItemWithBoost"):
        template = assets.templates[template_name]
        if template is None:
            continue
        for item in template.assets:
            if item.guid in seen or item.find(CONDITION_PATH) is None:
                continue
            seen.add(item.guid)
            if parser.parse(item) == FALLBACK_TEXT:
                unhandled.append(item)
    return unhandled


def dump_condition(item: Asset) -> None:
    name = item.text.values.get("english", item.name) if item.text else item.name
    print(f"=== {item.guid} {name} ===")
    condition_attr = item.find(CONDITION_PATH)
    if condition_attr is not None:
        condition_attr.print_tree()  # type: ignore
    else:
        print("(no boost condition on this item)")
    print()


def main() -> None:
    config = Config.from_json(ROOT / "config.json")
    assets = AssetCache.load(config)
    parser = BoostConditionParser(assets, assets.texts)

    guid_args = [int(g) for g in sys.argv[1:]]
    if guid_args:
        targets: list[Asset] = []
        for guid in guid_args:
            item = assets[guid]
            if item is None:
                print(f"GUID {guid} not found")
                continue
            targets.append(item)
    else:
        targets = find_unhandled(assets, parser)

    if not targets:
        print("No items with unhandled ('Boost condition active') boost conditions found.")
        return

    print(f"{len(targets)} item(s):\n")
    for item in targets:
        dump_condition(item)


if __name__ == "__main__":
    main()
