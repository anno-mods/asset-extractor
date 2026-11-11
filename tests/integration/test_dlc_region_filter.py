"""Regression tests for assetextractor.conversion.calculator.dlc_region_filter.

Covers a bug where an all-region asset (e.g. Silo, Silica) was wrongly excluded
from params.js because it listed an excluded region (Egyptian) alongside
allowed ones (Roman, Celtic): the filter must only drop content that is
*exclusively* gated behind excluded DLCs/regions, not content that merely also
appears there.
"""

from assetextractor.conversion.calculator.dlc_region_filter import (
    excluded_regions_for,
    filter_params_by_dlc,
    is_dlc_content_included,
)

ALLOWED_DLC_GUIDS = {67902, 67903}  # DLC01, DLC02
EXCLUDED_DLC_GUID = 67904  # DLC03 (Egypt)
EXCLUDED_REGIONS = {"Egyptian"}


def test_all_region_asset_is_kept():
    """Silo/Silica-style asset available in every region must not be dropped
    just because one of its regions (Egyptian) is excluded."""
    assert is_dlc_content_included(
        dlc_unlocks=[],
        regions=["Roman", "Celtic", "Egyptian"],
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_egypt_exclusive_region_asset_is_excluded():
    assert not is_dlc_content_included(
        dlc_unlocks=[],
        regions=["Egyptian"],
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_egypt_exclusive_scalar_region_is_excluded():
    assert not is_dlc_content_included(
        dlc_unlocks=[],
        regions="Egyptian",
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_no_region_constraint_is_kept():
    assert is_dlc_content_included(
        dlc_unlocks=[],
        regions=None,
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )
    assert is_dlc_content_included(
        dlc_unlocks=[],
        regions=[],
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_base_game_asset_no_dlc_unlocks_is_kept():
    assert is_dlc_content_included(
        dlc_unlocks=[],
        regions="Roman",
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_allowed_dlc_asset_is_kept():
    assert is_dlc_content_included(
        dlc_unlocks=[67903],
        regions=None,
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_disallowed_dlc_only_is_excluded():
    assert not is_dlc_content_included(
        dlc_unlocks=[EXCLUDED_DLC_GUID],
        regions=None,
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_multi_dlc_unlock_kept_if_any_allowed():
    """Content unlockable via *either* an allowed or disallowed DLC (e.g. shared
    across two DLC bundles) must be kept if at least one path is allowed."""
    assert is_dlc_content_included(
        dlc_unlocks=[EXCLUDED_DLC_GUID, 67903],
        regions=None,
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_dlc_gate_and_region_gate_both_exclusive_is_excluded():
    assert not is_dlc_content_included(
        dlc_unlocks=[EXCLUDED_DLC_GUID],
        regions=["Egyptian"],
        allowed_dlc_guids=ALLOWED_DLC_GUIDS,
        excluded_regions=EXCLUDED_REGIONS,
    )


def test_excluded_regions_for_threshold():
    dlc_region_map = {"dlc01": "Roman", "dlc02": "Roman", "dlc03": "Egyptian"}
    assert excluded_regions_for(dlc_region_map, include_dlcs_up_to=2) == {"Egyptian"}
    assert excluded_regions_for(dlc_region_map, include_dlcs_up_to=3) == set()
    assert excluded_regions_for(dlc_region_map, include_dlcs_up_to=0) == {"Roman", "Egyptian"}


def test_filter_params_by_dlc_keeps_all_region_entries_and_drops_exclusive():
    params = {
        "products": [
            {"guid": 1, "dlcUnlocks": [], "associatedRegions": ["Roman", "Celtic", "Egyptian"]},  # Silo-like
            {"guid": 2, "dlcUnlocks": [], "associatedRegions": ["Egyptian"]},  # Egypt-exclusive good
            {"guid": 3, "dlcUnlocks": [], "associatedRegions": ["Roman"]},  # base game
        ],
        "dlcs": [{"guid": 67902, "id": "DLC01"}],  # no dlcUnlocks/associatedRegions/region key -> untouched
    }

    removed = filter_params_by_dlc(params, ALLOWED_DLC_GUIDS, EXCLUDED_REGIONS)

    remaining_guids = {entry["guid"] for entry in params["products"]}
    assert remaining_guids == {1, 3}
    assert removed == {"products": 1}
    assert params["dlcs"] == [{"guid": 67902, "id": "DLC01"}]
