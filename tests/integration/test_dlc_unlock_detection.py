import pytest
from assetextractor.parsing.core.assets import AssetCache

def test_dlc_unlock_detection(assets: AssetCache):
    """Test that DLC unlock detection works for various strategies."""
    
    # Strategy 7/8: Patron -> Items (Vulcan example)
    # PatronVulcanus (144800) should be DLC01 (67902)
    vulcan = assets.elements.get(144800)
    assert vulcan is not None
    assert 67902 in vulcan.unlocked_by_dlcs
    
    # Strategy 1b/1c: Egyptian Good (Dates example)
    # Good Egyptian Dates (151680) should be DLC03 (67904)
    dates = assets.elements.get(151680)
    assert dates is not None
    assert 67904 in dates.unlocked_by_dlcs
    
    # Strategy 1: Icon path
    # Some dlc01 icon asset
    # Let's find one that has /dlc01/ in its icon path
    dlc01_assets = [a for a in assets.elements.values() 
                    if a.icon and "/dlc01/" in str(a.icon.value).lower().replace("\\", "/")]
    if dlc01_assets:
        for a in dlc01_assets:
            # Skip if it's hall_of_fame
            if "hall_of_fame" in str(a.icon.value).lower():
                continue
            assert 67902 in a.unlocked_by_dlcs
            
    # Strategy 2: UplayProductUnlocks
    # Check DLC01 cosmestics if any
    dlc01 = assets.elements.get(67902)
    if dlc01:
        unlocks = dlc01.dlc_unlocks
        assert len(unlocks) > 0
        for ref in unlocks.values():
            assert 67902 in ref.source.unlocked_by_dlcs

def test_base_sessions_not_dlc_tagged(assets: AssetCache):
    """Base-game sessions must not be DLC-tagged by cross-region unlock triggers.

    Egypt (DLC03) ships triggers 'Unlock Trigger Roman/Celtic Province from Egypt'
    whose ConditionIsDLCActive=DLC03 and ActionUnlockAsset unlock the base sessions
    Latium (3245, Roman) and Albion (6627, Celtic). These merely grant an additional
    travel route to sessions that already exist in the base game, so the sessions
    themselves must stay untagged. The genuine Egyptian session (149679) must remain
    tagged.
    """
    latium = assets.elements.get(3245)
    albion = assets.elements.get(6627)
    assert latium is not None
    assert albion is not None
    assert dict(latium.unlocked_by_dlcs) == {}, latium.unlocked_by_dlcs
    assert dict(albion.unlocked_by_dlcs) == {}, albion.unlocked_by_dlcs

    egypt_session = assets.elements.get(149679)
    assert egypt_session is not None
    assert 67904 in egypt_session.unlocked_by_dlcs


def test_base_goods_in_dlc_research_pools_not_dlc_tagged(assets: AssetCache):
    """Base-game goods listed in DLC03 research pools must stay untagged.

    The pools 'Asset Pool Research Greco Roman Soap/Wine' (rewards of the DLC03 soap and
    wine production techs) contain base goods that Egypt may merely produce. Genuine DLC
    goods (DLC01 Obsidian/Idols/Boardgames, Egyptian goods) are tagged via their icon path.
    """
    for guid in (2070, 2071, 2076, 2132, 2138, 2143):
        good = assets.elements.get(guid)
        assert good is not None
        assert dict(good.unlocked_by_dlcs) == {}, (guid, good.unlocked_by_dlcs)

    for guid, dlc in ((145102, 67902), (145220, 67902), (145221, 67902), (151712, 67904)):
        good = assets.elements.get(guid)
        assert good is not None
        assert dlc in good.unlocked_by_dlcs, guid

    # Non-product pool members (Egyptian-region building variants) stay tagged.
    wine_production = assets.elements.get(152387)
    assert wine_production is not None
    assert 67904 in wine_production.unlocked_by_dlcs


def test_dlc_bidirectional_references(assets: AssetCache):
    """Test that DLC references are correctly populated in both directions."""
    # Find any asset with DLC unlocks
    dlc_tagged_assets = [a for a in assets.elements.values() if a.unlocked_by_dlcs]
    assert len(dlc_tagged_assets) > 0
    
    for asset in dlc_tagged_assets[:10]: # Check first 10
        for dlc_guid, ref in asset.unlocked_by_dlcs.items():
            dlc_asset = ref.source
            assert dlc_guid == dlc_asset.guid
            assert asset.guid in dlc_asset.dlc_unlocks
            assert dlc_asset.dlc_unlocks[asset.guid].source == asset
