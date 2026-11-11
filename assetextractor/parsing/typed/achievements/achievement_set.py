from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.core.assets import Asset

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute
    from assetextractor.parsing.typed.achievements.achievement import Achievement


@dataclass(frozen=True)
class AchievementSetBaseInfo:
    """The processed 'AchievementSet' properties as one single object."""

    achievements: List[Achievement]


class AchievementSet(Asset, template_names="AchievementSet"):
    """
    Base class for assets that contain a 'AchievementSet' property.
    This consolidates the extraction, formatting, and printing of additional attributes.
    """

    @cached_property
    def achievements(self) -> List[Achievement]:
        ach_list = cast("ListAttribute | None", self.find_value("AchievementSet.Achievements"))
        if not ach_list:
            return []

        resolved_ach = (ach.find_ref("Asset") for ach in ach_list)
        return [cast("Achievement", a) for a in resolved_ach if a is not None]

    @cached_property
    def achievement_set_info(self) -> AchievementSetBaseInfo:
        """The structured 'AchievementSet' data."""
        return AchievementSetBaseInfo(achievements=self.achievements)
