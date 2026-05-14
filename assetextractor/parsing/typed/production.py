from __future__ import annotations

from assetextractor.parsing.typed.cost import AssetWithCosts


class Production(AssetWithCosts, template_names="Production"):
    """
    Specialized Asset for 'Production' with pre-computed data.

    Examples:
        - GUID: 3174 -> Production Food Roman Bread.
    """

    pass


class ProductionField(AssetWithCosts, template_names="Production Field"):
    """
    Specialized Asset for 'Production Field' with pre-computed data.

    Examples:
        - GUID: 2693 -> Production Field Roman Wheat.
    """

    pass


class SlotFactoryBuilding7(AssetWithCosts, template_names="SlotFactoryBuilding7"):
    """
    Specialized Asset for 'SlotFactoryBuilding7' with pre-computed data.

    Examples:
        - GUID: 3075 -> Production Ingredient Roman Flour.
    """

    pass


class ProductionArea(AssetWithCosts, template_names="Production Area"):
    """
    Specialized Asset for 'ProductionArea' with pre-computed data.

    Examples:
        - GUID: 5975 -> Production Meadow Celtic Dartmoor Ponies.
    """

    pass
