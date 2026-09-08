"""Tests for assetextractor.parsing.core.texts.strip_html_tags."""

from assetextractor.parsing.core.texts import strip_html_tags


def test_plain_text_unchanged():
    assert strip_html_tags("Rome was not built in a day") == "Rome was not built in a day"


def test_strips_real_tag_preserves_inner_text():
    assert strip_html_tags("<color=#fff>Rome</color>") == "Rome"


def test_preserves_stray_bare_angle_brackets():
    text = "tier < 3 and progress > 50%"
    assert strip_html_tags(text) == text


def test_strips_multiple_tags_in_sequence():
    assert strip_html_tags("<b>Bold</b> and <i>italic</i>") == "Bold and italic"


def test_strips_tag_with_attributes():
    assert strip_html_tags("<font color='#FFFFFF'>text</font>") == "text"


def test_empty_string_returns_empty_string():
    assert strip_html_tags("") == ""
