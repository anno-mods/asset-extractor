from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.attributes import ListAttribute, PrimitiveAttribute, ReferenceAttribute

if TYPE_CHECKING:
    import lxml.etree as et

    from assetextractor.parsing.core.assets import AssetCache


@dataclass(frozen=True)
class Maintenance:
    product: str  # Localized name
    amount: int


class AssetWithMaintenance(Asset):
    """Base class for assets that contain a 'Maintenance.Maintenances' list."""

    def __init__(self, node: et._Element, cache: AssetCache):
        # This call is CRITICAL. Without it, self.template and self.cache
        # will not exist on this object.
        super().__init__(node, cache)

    @cached_property
    def maintenance_costs(self) -> List[tuple[Asset, int]]:
        """Parses raw 'Maintenance.Maintenances' into (Asset, Amount) tuples."""
        raw_list = self.find("Maintenance.Maintenances")
        out_list: List[tuple[Asset, int]] = []

        if self.guid == 43664:  # Troop Roman Murmillo Gladiator
            print(f"***** Computed Maintenance Cost -> {self.guid} Troop Roman Murmillo Gladiator *****")
            # self.print_meta_tree()
            print(raw_list)
        if self.guid == 37553:  # Troop Roman Celtic Auxilia
            print(f"***** Computed Maintenance Cost -> {self.guid} Troop Roman Celtic Auxilia *****")
            print(raw_list)

        if isinstance(raw_list, ListAttribute):
            for item in raw_list:
                product_ref = item.find("Product")
                amount_node = item.find("Amount")

                # Default amount to 0 if tag is missing.
                amount_val = (
                    amount_node.value
                    if isinstance(amount_node, PrimitiveAttribute) and isinstance(amount_node.value, int)
                    else 0
                )

                if isinstance(product_ref, ReferenceAttribute):
                    product_asset = self.cache.get(product_ref.guid)
                    # TODO: Add the class 'Product' here when implemented.
                    if isinstance(product_asset, Asset):
                        out_list.append((product_asset, amount_val))

        return out_list

    @cached_property
    def formatted_maintenance_costs(self) -> List[Maintenance]:
        """Converts assets into localized Maintenance dataclasses."""
        return [
            Maintenance(product=asset.text() if asset.text is not None else asset.name, amount=amt)
            for asset, amt in self.maintenance_costs
        ]
