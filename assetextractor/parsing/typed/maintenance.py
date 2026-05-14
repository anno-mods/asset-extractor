from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.core.assets import Asset

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


@dataclass(frozen=True)
class Maintenance:
    product: str
    amount: int


class AssetWithMaintenance(Asset):
    """Base class for assets that contain a 'Maintenance.Maintenances' list."""

    @cached_property
    def maintenance_costs(self) -> List[tuple[Asset, int]]:
        out: List[tuple[Asset, int]] = []
        for entry in cast("ListAttribute", self.find("Maintenance.Maintenances")):
            product_asset = entry.find_ref("Product")
            amount = cast(int, entry.find_value("Amount") or 0)
            if product_asset is not None:
                out.append((product_asset, amount))
        return out

    @cached_property
    def formatted_maintenance_costs(self) -> List[Maintenance]:
        return [Maintenance(product=asset.short_description, amount=amt) for asset, amt in self.maintenance_costs]
