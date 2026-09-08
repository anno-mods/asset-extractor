"""Tests for AssetWithBuilding.origin_hint_ui's use of the shared tag-stripping helper."""

from assetextractor.parsing.typed.common.building import AssetWithBuilding

_origin_hint_ui = AssetWithBuilding.origin_hint_ui.func


class _FakeText:
    def __init__(self, value: str):
        self._value = value

    def __call__(self) -> str:
        return self._value


class _FakeHintAsset:
    def __init__(self, text_value: str | None):
        self.text = _FakeText(text_value) if text_value is not None else None


class _FakeBuildingInfo:
    def __init__(self, origin_hint):
        self.origin_hint = origin_hint


class _FakeAssetWithBuilding:
    def __init__(self, building_info: _FakeBuildingInfo):
        self.building_info = building_info


def test_real_markup_is_stripped():
    asset = _FakeAssetWithBuilding(_FakeBuildingInfo(_FakeHintAsset("<color=#fff>Prophecies of Ash</color>")))
    assert _origin_hint_ui(asset) == "Prophecies of Ash"


def test_bare_angle_brackets_preserved():
    asset = _FakeAssetWithBuilding(_FakeBuildingInfo(_FakeHintAsset("tier < 3 and progress > 50%")))
    assert _origin_hint_ui(asset) == "tier < 3 and progress > 50%"


def test_no_origin_hint_asset_falls_back_to_base():
    asset = _FakeAssetWithBuilding(_FakeBuildingInfo(None))
    assert _origin_hint_ui(asset) == "Base"


def test_hint_asset_with_no_text_falls_back_to_base():
    asset = _FakeAssetWithBuilding(_FakeBuildingInfo(_FakeHintAsset(None)))
    assert _origin_hint_ui(asset) == "Base"
