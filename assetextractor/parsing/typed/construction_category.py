from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, List  # Postpones evaluation of annotations

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.attributes import ListAttribute, ReferenceAttribute

# Import AssetCache ONLY for type checking
if TYPE_CHECKING:
    import lxml.etree as et

    from assetextractor.parsing.core.assets import AssetCache
    from assetextractor.parsing.core.texts import Text


class ConstructionCategory(Asset):
    """Specialized Asset for Construction Category with pre-computed data."""

    def __init__(self, node: et._Element, cache: AssetCache):
        super().__init__(node, cache)

    @cached_property
    def building_assets(self) -> List[Asset]:
        """
        Lazily resolves and caches the list of assets in this category.
        The work only happens the first time this property is accessed.
        """
        building_list = self.find("ConstructionCategory.BuildingList")

        if not isinstance(building_list, ListAttribute):
            return []

        # We use a list comprehension to flatten the logic:
        # 1. Find the "Building" reference in each item
        # 2. Get the GUID
        # 3. Resolve the asset from the cache
        return [
            asset
            for item in building_list
            # 1. Narrow 'ref' to ReferenceAttribute to access .guid
            if isinstance(ref := item.find("Building"), ReferenceAttribute)
            # 2. Narrow 'asset' to Asset (from NamedElement) to access its properties
            and isinstance(asset := self.cache.get(ref.guid), Asset)
        ]

    def _get_text_from_node(self, path: str, fallback: str) -> str:
        """Helper to resolve a Text node path into a localized string."""
        node = self.find(path)

        if node is not None:
            lang = self.cache.texts.converter.language
            text_attr: Text | None = node()
            if text_attr is not None:
                # Return the localized string, fallback to English, then to the provided default
                return text_attr.get(lang) or text_attr.get("english") or fallback  # type: ignore

        return fallback

    @cached_property
    def localized_title(self) -> str:
        """Lazily fetches the title based on the active converter language."""
        # 'self.text' is automatically mapped to "Text.OasisId" by the library
        return self._get_text_from_node("Text.OasisId", "No Title")
