---
name: boost-condition-check-and-fix
description: Use when an Anno 117 item's extracted boost_condition falls back to the generic "Boost condition active" string, or when adding support for a new BoostCondition/PreConditionList condition type (ConditionXxx) in this repo's item extractor.
---

# Boost Condition Check and Fix

## Overview

`ItemWithBoost` assets gate their boost buffs behind a condition at
`ItemWithBoost.BoostCondition.PreConditionList.Condition`. `BoostConditionParser`
(`assetextractor/conversion/statistics/boost_conditions.py`) turns that raw
structure into a human-readable string. Any `ConditionXxx` type it doesn't
recognize silently falls back to the literal string `"Boost condition active"`
in the exported CSV — that string is the symptom to grep for.

## Efficiency rule: don't reload the asset cache repeatedly

`AssetCache.load(config)` parses the full cached XML tree and takes **~30-55s**.
Every `uv run python -c "..."` one-liner pays that cost again. Two ways to avoid
paying it more than once per session:

1. **Prefer the pre-built asset browser for reading a condition you already
   have the GUID for.** Every asset has a static, pre-rendered HTML file at
   `<assetbrowser_dir>/assets/<guid>.html` (get `assetbrowser_dir` from
   `config.json`, typically `C:/assetbrowser`) — e.g. `C:/assetbrowser/assets/160060.html`.
   It already contains the fully resolved inheritance tree, same content as
   `print_tree()`, with **zero Python startup cost**. Read it directly; don't
   spin up a script just to look at one asset's structure.
2. **When you need a scan across many items (finding *which* GUIDs are
   unhandled) or the asset browser is stale/missing an item, use the bundled
   script** — it loads the cache exactly once and can both scan and dump in
   the same process:
   ```bash
   # Full scan: find every item still using the generic fallback, dump each one's Condition tree
   uv run python .claude/skills/boost-condition-check-and-fix/scripts/check_boost_conditions.py

   # Targeted: dump specific GUIDs only (skips the scan, still one load)
   uv run python .claude/skills/boost-condition-check-and-fix/scripts/check_boost_conditions.py 160060 156726
   ```
   Never call this script once per GUID — pass all GUIDs you need in a single invocation.

If the asset browser looks stale (game updated, new items expected), regenerate
it via `new_version.bat` (see `docs/development.md` "Release Workflow") — that
is the authoritative pipeline for the browser and the versioned items CSV.
Don't run it just to inspect one condition; only when the underlying game data
has actually changed.

## Workflow

1. **Check**: run the script with no arguments (or grep an already-exported
   CSV in `results/tables/` for `"Boost condition active"`) to get the list of
   unhandled GUIDs. The script's output already includes each item's raw
   Condition tree, so this single run usually gives you everything needed for
   step 2 too.
2. **Understand the structure**: from the printed tree (or the asset browser
   page), identify the `ConditionXxx` attribute name and its fields. Cross-check
   field names/types against `.cache-117/data/base/config/export/properties-meta.xml`
   (search for `<Name>ConditionXxx</Name>`) if a field's purpose isn't obvious
   from its name — this file lists each `ValueDefinition`'s `DataType` and, for
   `Variable` types, the wrapper struct (`BoolVariableOrValue`, `IntVariableOrValue`,
   `FloatVariableOrValue`, `AssetVariableOrValue`, `StringVariableOrValue`, each
   holding a literal field + a `*VariableName` field for the session-variable case).
3. **Fix**: add a `_parse_<ConditionName>` method to `BoostConditionParser` in
   `boost_conditions.py`, following the existing methods as templates:
   - Use `condition.find("ConditionXxx")` + `isinstance(x, (TemplateAttribute, DictAttribute, Property))`
     rather than direct attribute access (`condition.ConditionXxx`) — direct
     access on `TemplateAttribute` isn't statically typed and trips pyright
     (`reportAttributeAccessIssue`/`reportUnknownMemberType`).
   - Use `self.find_val(obj, "Path.To.Field", expected_type)` for scalars and
     `obj.find_ref("Path.To.Field")` for `Asset` references, matching every
     other `_parse_*` method in the file.
   - Register the new method in the `parsers` list inside `parse()`, **before**
     `self._parse_always_true` (that one must stay last).
   - Add the new `ConditionXxx` name to the `has_other` guard list inside
     `_parse_always_true` so it doesn't spuriously claim "Always active" when
     paired with `ConditionAlwaysTrue`.
4. **Document**: add the new condition type to `docs/conditions.md` (format,
   example, and its number in both the `### N. ConditionXxx` list and the
   "Condition Priority" ordered list).
5. **Verify** (single cache load each):
   ```bash
   uv run python .claude/skills/boost-condition-check-and-fix/scripts/check_boost_conditions.py
   uv run python -m pytest tests/integration/test_boost_conditions.py -v
   ```
   The scan script should report zero remaining items; `test_no_generic_boost_conditions`
   and `test_all_condition_types_covered` should pass. (A pre-existing, unrelated
   failure in `test_specific_need_attribute_conditions` — "Income" vs "Money" for
   GUID 41360 — is a stale expectation, not a regression to chase here.)
6. Only regenerate the versioned CSV (`new_version.bat`, or directly
   `uv run python -m assetextractor.conversion.statistics.extract_items_to_csv --version "X"`)
   once the fix is verified — that command also does a full ~30-55s cache load,
   so don't run it speculatively.

## Common mistakes

- Writing a throwaway `uv run python -c "..."` per GUID — each one reloads
  the cache. Batch GUIDs into one script call, or read the asset browser page.
- Accessing `condition.ConditionXxx` directly instead of `condition.find("ConditionXxx")`
  — works at runtime but fails `uv run nox -s pyright`.
- Forgetting to add the new condition name to `_parse_always_true`'s guard list.
- Chasing the pre-existing "Income"/"Money" failure in
  `test_specific_need_attribute_conditions` (GUID 41360) — unrelated stale
  expectation, not a regression from a condition-parser change.
