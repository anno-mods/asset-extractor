"""Tests for Asset.short_description's strip-before-truncate ordering."""

from assetextractor.parsing.core.assets import Asset

_short_description = Asset.short_description.fget


class _FakeText:
    def __init__(self, value: str):
        self._value = value

    def __call__(self) -> str:
        return self._value


class _FakeAsset:
    """Minimal stand-in exposing only what short_description reads."""

    def __init__(self, text: str | None, name: str = "FakeName", identifier: str = "FakeIdentifier"):
        self.text = _FakeText(text) if text is not None else None
        self.name = name
        self.identifier = identifier


def test_short_text_without_markup_unchanged():
    asset = _FakeAsset("Rome was not built in a day")
    assert _short_description(asset) == "Rome was not built in a day"


def test_long_text_with_tag_before_cutoff_is_stripped_and_truncated():
    text = "<b>Rome</b> " + "x" * 130
    asset = _FakeAsset(text)
    result = _short_description(asset)
    assert "<" not in result
    assert ">" not in result
    assert result.endswith("...")


def test_long_text_with_tag_straddling_cutoff_has_no_dangling_fragment():
    # Place an opening tag so its raw text position straddles the 120-char
    # truncation boundary; strip-before-truncate must remove it entirely
    # before the cutoff is applied, leaving no unterminated "<...".
    prefix = "x" * 115
    text = prefix + "<color=#fff>label</color>" + "y" * 20
    asset = _FakeAsset(text)
    result = _short_description(asset)
    assert "<" not in result
    assert ">" not in result


def test_no_text_falls_back_to_name():
    asset = _FakeAsset(None, name="FakeName")
    assert _short_description(asset) == "FakeName"


def test_exact_120_char_stripped_text_has_no_ellipsis():
    text = "x" * 120
    asset = _FakeAsset(text)
    result = _short_description(asset)
    assert result == text
    assert not result.endswith("...")
