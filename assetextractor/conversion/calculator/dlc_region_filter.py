"""DLC/region inclusion filter for params.js generation.

Extracted from conversion_calculator.ipynb so the logic is unit-testable outside
a notebook kernel. Two independent signals decide whether an asset belongs in
params.js:

1. ``dlcUnlocks`` tagging (populated by the 9-strategy DLC detection in
   ``assetextractor.parsing.core.dlc_detection`` for most explicitly-unlocked
   content).
2. ``associatedRegions``/``region`` (raw region literals like "Roman",
   "Celtic", "Egyptian") checked against a DLC-to-region map, for content a
   brand-new region introduces that the unlock-link-based detection above
   doesn't reach (nothing references it via an UplayProductUnlocks-style link
   yet).

An asset must be excluded by *both* signals to be dropped: an item available
in every region (e.g. Silo, Silica) lists all regions including an excluded
one, but is not DLC-exclusive, so it must be kept.
"""

from __future__ import annotations


def is_dlc_content_included(
    dlc_unlocks: list[int] | None,
    regions: str | list[str] | None,
    allowed_dlc_guids: set[int],
    excluded_regions: set[str],
) -> bool:
    """Return False only if content is exclusively gated behind an excluded DLC/region.

    - ``dlc_unlocks``: keep if empty (base game) or unlockable via at least one
      allowed DLC, even if it's *also* tagged with a disallowed one.
    - ``regions``: keep if empty/None (no region constraint) or if at least one
      listed region is not excluded (available in an allowed region too).
      Only exclude when every listed region is excluded.
    """
    if dlc_unlocks and not any(guid in allowed_dlc_guids for guid in dlc_unlocks):
        return False

    if regions:
        region_list = regions if isinstance(regions, list) else [regions]
        if region_list and all(region in excluded_regions for region in region_list):
            return False

    return True


def excluded_regions_for(dlc_region_map: dict[str, str], include_dlcs_up_to: int) -> set[str]:
    """Regions belonging to a DLC numbered above ``include_dlcs_up_to``."""
    import re

    excluded: set[str] = set()
    for prefix, region in dlc_region_map.items():
        match = re.search(r"dlc(\d+)", prefix)
        if match and int(match.group(1)) > include_dlcs_up_to:
            excluded.add(region)
    return excluded


def filter_params_by_dlc(
    params: dict[str, object],
    allowed_dlc_guids: set[int],
    excluded_regions: set[str],
) -> dict[str, int]:
    """Filter every top-level list in ``params`` in place. Returns {key: removed_count}."""
    removed_counts: dict[str, int] = {}
    for key, value in params.items():
        if not (isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict)):
            continue
        first = value[0]
        if not ("dlcUnlocks" in first or "associatedRegions" in first or "region" in first):
            continue

        before = len(value)
        filtered = [
            entry
            for entry in value
            if is_dlc_content_included(
                entry.get("dlcUnlocks"),
                entry.get("associatedRegions", entry.get("region")),
                allowed_dlc_guids,
                excluded_regions,
            )
        ]
        params[key] = filtered
        removed = before - len(filtered)
        if removed:
            removed_counts[key] = removed

    return removed_counts
