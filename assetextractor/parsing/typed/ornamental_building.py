from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING  # Postpones evaluation of annotations

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.attributes import ListAttribute, PrimitiveAttribute

# Import AssetCache ONLY for type checking
if TYPE_CHECKING:
    import lxml.etree as et

    from assetextractor.parsing.core.assets import AssetCache
    from assetextractor.parsing.core.texts import Text


class OrnamentalBuilding(Asset):
    """Specialized Asset for Ornamental Buildings with pre-computed data."""

    def __init__(self, node: et._Element, cache: AssetCache):
        super().__init__(node, cache)

        # Pre-compute Costs
        self.costs = []

        # Navigating the Anno structure: Cost -> Costs
        # find() returns the Property/Attribute object
        costs_list = self.find("Cost.Costs")

        # In this library, ListAttributes (arrays in XML) are iterable
        if isinstance(costs_list, ListAttribute):
            for item in costs_list:
                # 'item' represents an <Item> in the XML
                # Find the 'Amount' within the 'Cost' item
                amount = item.find("Amount")
                if amount:
                    # Calling the attribute object () returns the int/float value
                    self.costs.append(amount() or 0)  # type: ignore

        # 2. Pre-compute Prestige
        prestige_node = self.find("Ornament.OrnamentUnit")
        if isinstance(prestige_node, PrimitiveAttribute):
            self.prestige = int(prestige_node.value) if prestige_node and prestige_node.value else 0

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
    def costs(self) -> list[float]:
        """
        Maps <Values><Cost><Costs> list to a flat list of amounts.
        Processed only on-demand.
        """
        costs_list = self.find("Cost.Costs")
        if not isinstance(costs_list, ListAttribute):
            return []

        # List comprehension handles the <Item><Amount> mapping
        return [
            float(val) if (val := amount()) is not None else 0.0
            for item in costs_list
            if isinstance(amount := item.find("Amount"), PrimitiveAttribute)
        ]

    @cached_property
    def prestige(self) -> int:
        """
        Maps <Values><Ornament><OrnamentUnit> to an integer.
        Processed only on-demand.
        """
        unit_node = self.find("Ornament.OrnamentUnit")

        # We check for the node and then the value
        if isinstance(unit_node, PrimitiveAttribute) and unit_node.value is not None:
            try:
                return int(unit_node.value)
            except (ValueError, TypeError):
                return 0
        return 0

    @cached_property
    def localized_title(self) -> str:
        """Lazily fetches the title based on the active converter language."""
        # 'self.text' is automatically mapped to "Text.OasisId" by the library
        return self._get_text_from_node("Text.OasisId", "No Title")

    @cached_property
    def localized_description(self) -> str:
        """Lazily fetches the description based on the active converter language."""
        return self._get_text_from_node("Ornament.OrnamentDescription", "No Description")
