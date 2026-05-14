from __future__ import annotations

from typing import TYPE_CHECKING

from assetextractor.parsing.core.asset_factories.common.cost import AssetWithCosts
from assetextractor.parsing.core.asset_factories.common.maintenance import AssetWithMaintenance

if TYPE_CHECKING:
    import lxml.etree as et

    from assetextractor.parsing.core.assets import AssetCache


class LandUnit(AssetWithCosts, AssetWithMaintenance):
    """
    Specialized Asset for 'LandUnit' with pre-computed data.

    Examples:
        - GUID: 37475 -> Troop Roman Auxilia.
    """

    def __init__(self, node: et._Element, cache: AssetCache):
        # MRO Chain: LandUnit -> AssetWithCosts -> AssetWithMaintenance -> Asset
        super().__init__(node, cache)
