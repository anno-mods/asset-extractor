"""Tests for AchievementExtractor.export_all_achievement_assets dedup behavior."""

from assetextractor.conversion.statistics.achievement_extractor import AchievementExtractor
from assetextractor.conversion.statistics.icon_processor import IconProcessor


class _FakeAchievement:
    def __init__(self, guid: int):
        self.guid = guid


class _FakeAchievementSet:
    def __init__(self, achievements):
        self.achievements = achievements


def _make_extractor(achievement_sets: dict) -> AchievementExtractor:
    extractor = object.__new__(AchievementExtractor)
    extractor.achievement_sets = achievement_sets
    return extractor


def _capture_export_icons(monkeypatch):
    captured = {}

    def fake_export_icons(assets, **kwargs):
        captured["assets"] = list(assets)
        return {"exported": len(assets), "skipped": 0, "errors": 0}

    monkeypatch.setattr(IconProcessor, "export_icons", staticmethod(fake_export_icons))
    return captured


def test_achievement_in_single_set_exported_once(monkeypatch):
    captured = _capture_export_icons(monkeypatch)
    ach = _FakeAchievement(1)
    extractor = _make_extractor({100: _FakeAchievementSet([ach])})

    extractor.export_all_achievement_assets(output_base="unused")

    assert captured["assets"] == [ach]


def test_achievement_shared_across_sets_appears_once(monkeypatch):
    captured = _capture_export_icons(monkeypatch)
    shared = _FakeAchievement(42)
    extractor = _make_extractor(
        {
            100: _FakeAchievementSet([shared]),
            101: _FakeAchievementSet([shared, _FakeAchievement(2)]),
        }
    )

    extractor.export_all_achievement_assets(output_base="unused")

    guids = [a.guid for a in captured["assets"]]
    assert guids.count(42) == 1
    assert len(captured["assets"]) == 2


def test_empty_achievement_sets_triggers_extract_all(monkeypatch):
    captured = _capture_export_icons(monkeypatch)
    extractor = _make_extractor({})

    fallback_ach = _FakeAchievement(7)

    def fake_extract_all():
        extractor.achievement_sets = {200: _FakeAchievementSet([fallback_ach])}
        return extractor.achievement_sets

    extractor.extract_all = fake_extract_all

    extractor.export_all_achievement_assets(output_base="unused")

    assert captured["assets"] == [fallback_ach]
