from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.core.assets import Asset

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


@dataclass(frozen=True)
class Cost:
    ingredient: str
    """The ingredient (material) as localized text. Usually 'Denarii' + others
    like 'Timber', 'Marble', etc."""
    amount: int
    """Required quantity of this ingredient."""


class AssetWithCosts(Asset):
    """Base class for assets that contain a 'Cost.Costs' list."""

    @cached_property
    def costs(self) -> List[tuple[Asset, int]]:
        out: List[tuple[Asset, int]] = []
        for entry in cast("ListAttribute", self.find("Cost.Costs")):
            cost_asset = entry.find_ref("Ingredient")
            amount = cast(int, entry.find_value("Amount") or 0)
            if cost_asset is not None:
                out.append((cost_asset, amount))
        return out

    @cached_property
    def formatted_costs(self) -> List[Cost]:
        return [Cost(ingredient=asset.short_description, amount=amt) for asset, amt in self.costs]
