from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.typed.effect import Effect
from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.texts import Text

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


@dataclass(frozen=True)
class Milestone:
    devotion: int
    buff_scaling: int


@dataclass(frozen=True)
class LocalEffect:
    asset: Effect | None
    milestones: List[Milestone]
    title: str
    description: str


class Patron(Asset, template_names="Patron"):
    """Specialized Asset for Patron (Deities) with pre-computed data."""

    @cached_property
    def local_effects(self) -> List[LocalEffect]:
        """Maps the local effects into localized title and descriptions along with all the milestones."""
        parsed_effects: List[LocalEffect] = []

        for effect_item in cast("ListAttribute", self.find("Patron.LocalEffects")):
            effect_asset = cast(Effect | None, effect_item.find_ref("GUID"))

            milestones: List[Milestone] = [
                Milestone(
                    devotion=cast(int, mil.find_value("Devotion") or 0),
                    buff_scaling=cast(int, mil.find_value("BuffScaling") or 0),
                )
                for mil in cast("ListAttribute", effect_item.find("Milestones"))
            ]

            title_text = cast(Text | None, effect_item.find_value("Title"))
            desc_text = cast(Text | None, effect_item.find_value("Description"))
            parsed_effects.append(
                LocalEffect(
                    asset=effect_asset,
                    milestones=milestones,
                    title=title_text() if title_text else "No Title",
                    description=desc_text() if desc_text else "No Title",
                )
            )

        return parsed_effects
