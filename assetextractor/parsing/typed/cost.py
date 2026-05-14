from dataclasses import dataclass
from functools import cached_property
from typing import List

import lxml.etree as et

from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.attributes import ListAttribute, PrimitiveAttribute, ReferenceAttribute


@dataclass(frozen=True)
class Cost:
    ingredient: str
    """The ingredient (material) as localized text. Usually 'Denarii' + others
    like 'Timber', 'Marble', etc."""
    amount: int
    """Required quantity of this ingredient."""


class AssetWithCosts(Asset):
    """Base class for assets that contain a 'Cost.Costs' list."""

    def __init__(self, node: et._Element, cache: AssetCache):
        # This call is CRITICAL. Without it, self.template and self.cache
        # will not exist on this object.
        super().__init__(node, cache)

    @cached_property
    def costs(self) -> List[tuple[Asset, int]]:
        """Parses raw Cost.Costs into (Asset, Amount) tuples."""
        raw_cost_list = self.find("Cost.Costs")
        out_cost_list: List[tuple[Asset, int]] = []

        if isinstance(raw_cost_list, ListAttribute):
            for asset_entry in raw_cost_list:
                linked_ref = asset_entry.find("Ingredient")
                amount_node = asset_entry.find("Amount")

                amount_val = (
                    amount_node.value
                    if isinstance(amount_node, PrimitiveAttribute) and isinstance(amount_node.value, int)
                    else 0
                )

                if isinstance(linked_ref, ReferenceAttribute):
                    cost_asset = self.cache.get(linked_ref.guid)
                    if isinstance(cost_asset, Asset):
                        out_cost_list.append((cost_asset, amount_val))

        return out_cost_list

    @cached_property
    def formatted_costs(self) -> List[Cost]:
        """Converts assets into localized Cost dataclasses."""
        return [
            Cost(ingredient=asset.text() if asset.text is not None else asset.name, amount=amt)
            for asset, amt in self.costs
        ]
