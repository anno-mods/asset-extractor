from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

from assetextractor.parsing.typed.buildings import AssetBuildingBase

if TYPE_CHECKING:
    from assetextractor.parsing.core.texts import Text


class HippodromeBuilding(AssetBuildingBase, template_names="HippodromeBuilding"):
    """
    Specialized Asset for 'HippodromeBuilding' with pre-computed data.

    Examples:
        - GUID: 152714 -> Wonder Roman Hippodrome
    """

    @cached_property
    def localized_description(self) -> str:
        """Returns the ingame description of this building."""
        info_desc = cast("Text | None", self.find_value("Standard.InfoDescription"))

        return info_desc() if info_desc else "No Description"
