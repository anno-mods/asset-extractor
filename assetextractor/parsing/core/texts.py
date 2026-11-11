from __future__ import annotations

import re
import typing as t

import lxml.etree as et

from .common import Dataset, ElementCache, NamedElement

if t.TYPE_CHECKING:
    from pathlib import Path

    from assetextractor.parsing.core.assets import Asset

    from .attributes import Attribute


def parse_text_id(text: str) -> int:
    """Parse a text ID, supporting both decimal and hex (no prefix) formats."""
    try:
        return int(text)
    except ValueError:
        return int(text, 16)


_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")


def strip_html_tags(text: str) -> str:
    """Remove rich-text markup tags from localized text, e.g. '<color=#fff>Rome</color>' -> 'Rome'.

    Only matches spans starting with '<letter' or '</letter', so bare '<'/'>' characters
    used as comparison operators (e.g. 'tier < 3 and progress > 50%') are left untouched.
    """
    return _TAG_RE.sub("", text)


class Text(NamedElement["TextCache"]):
    """Represents all localized text versions with the same id from gui/texts_*.xml.
    Some texts contain html tags or placeholders for formatting. Use `has_html_escapes` and `count_format_args`. Note that `format` is not variadic but wants a list.
    """

    def __init__(self, node: et._Element, cache: TextCache):
        self.cache = cache
        self.id = self.get_id(node)
        self.values: dict[str, str] = {}
        self.node = node

        if (text_node := node.find("Text")) is not None:  # noqa: SIM102
            if text_node.text is not None:
                self.values["english"] = text_node.text
                return

        raise ValueError(f"Missing text: {self.id}")

    @staticmethod
    def get_id(node: et._Element) -> int:
        id_node = node.find("LineId")
        if id_node is None:
            id_node = node.find("GUID")

        if id_node is None or id_node.text is None:
            raise ValueError(f"Missing text id: {node.text}")

        return parse_text_id(id_node.text)

    def has_html_escapes(self) -> bool:
        attr = "_has_HTML_escapes"
        if not hasattr(self, attr):
            setattr(self, attr, "&lt;" in self.values["english"])
        return getattr(self, attr)

    def count_format_args(self):
        attr = "_count_format_args"
        if not hasattr(self, attr):
            setattr(self, attr, self.values["english"].count("{}"))
        return getattr(self, attr)

    def format(self, list: list[Text | Asset | Attribute[t.Any, t.Any] | str]):
        if len(list) != self.count_format_args():
            raise ValueError(
                f"Text has {self.count_format_args()} format placeholders but {len(list)} arguments were given for text: {str:r}"
            )

        args: list[Text | str] = []
        for arg in list:
            if isinstance(arg, str):
                args.append(arg)
                continue

            if hasattr(arg, "value"):  # Check for TextAttribute (which we cannot import due to cylic imports)
                val = getattr(arg, "value")
                if isinstance(val, Text):
                    arg = val
                else:
                    args.append(str(val))
                    continue

            if isinstance(arg, Text):
                args.append(arg)
                continue

            if hasattr(arg, "text"):
                arg = getattr(arg, "text")

            if isinstance(arg, Text):
                args.append(arg)
            else:
                raise ValueError(f"Could not convert {arg.full_path if not isinstance(arg, str) else 'None'} to text.")

        formatted = Text(self.node, self.cache)
        for language in self.cache.languages.literals:
            language = language.lower()
            formatted[language] = self.values[language].format(
                *[arg.values[language] if isinstance(arg, Text) else arg for arg in args]
            )

        return formatted

    def __getitem__(self, key: str) -> str | None:
        return self.values[key.lower()]

    def __setitem__(self, key: str, value: str):
        self.values[key.lower()] = value

    def __contains__(self, key: str) -> bool:
        return key in self.values

    def __call__(self) -> str:
        return self.cache.converter(self)

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self):
        return self.values["english"]


class TextCache(ElementCache[Text]):
    def __init__(self, folder_path: Path, languages: Dataset):
        super().__init__(folder_path, int)
        self.languages = languages
        self.converter = StandardTextConverter()

        texts_english = folder_path / "texts_english.xml"
        if not texts_english.exists():
            raise FileNotFoundError(f"File {texts_english} not found.")

        self.tree = et.parse(str(texts_english))

        for element in self.tree.xpath("//Texts/Text"):
            try:
                text = Text(element, self)
                self.elements[text.id] = text
            except ValueError:
                pass  # skip not yet defined texts

        for language in self.languages.literals:
            language = language.lower()
            if language == "english":
                continue

            path = folder_path / f"texts_{language}.xml"
            if not path.exists():
                continue

            tree = et.parse(str(path))

            for element in tree.xpath("//Texts/Text"):
                if Text.get_id(element) not in self.elements:
                    continue

                self.elements[Text.get_id(element)].values[language] = element.find("Text").text

    def add(self, element: Text):
        self.elements[element.id] = element


class StandardTextConverter:
    def __init__(self, language: str = "english"):
        self.language = language

    def __call__(self, text: Text) -> str:
        if self.language in text:
            return str(text[self.language])
        return str(text["english"])
