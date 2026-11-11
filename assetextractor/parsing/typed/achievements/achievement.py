from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, cast

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.typed.common.enums import AchievementDifficultyType

if TYPE_CHECKING:
    from assetextractor.parsing.core.texts import Text


@dataclass(frozen=True)
class AchievementBaseInfo:
    """The processed 'AchievementSet' properties as one single object."""

    achievement_title: str  # AchievementTitle
    achievement_description: str  # AchievementDescription
    achievement_difficulty: AchievementDifficultyType


class Achievement(Asset, template_names="Achievement"):
    """
    Base class for assets that contain a 'Achievement' property.
    This consolidates the extraction, formatting, and printing of additional attributes.
    """

    @cached_property
    def achievement_info(self) -> AchievementBaseInfo:
        """The structured 'Achievement' data."""
        a_title = cast("Text | None", self.find_value("Achievement.AchievementTitle"))
        a_description = cast("Text | None", self.find_value("Achievement.AchievementDescription"))
        a_diff = cast("AchievementDifficultyType | None", self.find_value("Achievement.AchievementDifficulty"))

        return AchievementBaseInfo(
            achievement_title=a_title() if a_title else self.name,
            achievement_description=a_description() if a_description else "",
            achievement_difficulty=a_diff or AchievementDifficultyType.BRONZE,
        )
