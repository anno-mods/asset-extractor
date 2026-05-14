from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.texts import Text

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


class OrnamentalBuilding(Asset, template_names=["OrnamentalBuilding", "PolygonObject"]):
    """Specialized Asset for Ornamental Buildings with pre-computed data."""

    @cached_property
    def costs(self) -> list[float]:
        return [
            float(cast(float, entry.find_value("Amount") or 0.0))
            for entry in cast("ListAttribute", self.find("Cost.Costs"))
        ]

    @cached_property
    def prestige(self) -> int:
        return int(cast(int, self.find_value("Ornament.OrnamentUnit") or 0))

    @cached_property
    def localized_title(self) -> str:
        text = cast(Text | None, self.find_value("Text.OasisId"))
        return text() if text else "No Title"

    @cached_property
    def localized_description(self) -> str:
        text = cast(Text | None, self.find_value("Ornament.OrnamentDescription"))
        return text() if text else "No Description"
