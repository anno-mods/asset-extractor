from __future__ import annotations

from assetextractor.parsing.core.asset_factories.common.cost import AssetWithCosts


class Production(AssetWithCosts):
    """
    Specialized Asset for 'Production' with pre-computed data.

    Examples:
        - GUID: 3174 -> Production Food Roman Bread.
    """

    pass


class ProductionField(AssetWithCosts):
    """
    Specialized Asset for 'Production Field' with pre-computed data.

    Examples:
        - GUID: 2693 -> Production Field Roman Wheat.
    """

    pass


class SlotFactoryBuilding7(AssetWithCosts):
    """
    Specialized Asset for 'SlotFactoryBuilding7' with pre-computed data.

    Examples:
        - GUID: 3075 -> Production Ingredient Roman Flour.
    """

    pass


class ProductionArea(AssetWithCosts):
    """
    Specialized Asset for 'ProductionArea' with pre-computed data.

    Examples:
        - GUID: 5975 -> Production Meadow Celtic Dartmoor Ponies.
    """

    pass
