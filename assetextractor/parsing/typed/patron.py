from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.attributes import FileNameAttribute, WandImageProto

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute
    from assetextractor.parsing.core.texts import Text
    from assetextractor.parsing.typed.buildings.mini_institution_building import MiniInstitutionBuilding
    from assetextractor.parsing.typed.common.asset_pool_base import AssetPoolBase
    from assetextractor.parsing.typed.effect import Effect


@dataclass(frozen=True)
class Milestone:
    devotion: int
    buff_scaling: int


@dataclass(frozen=True)
class LocalEffect:
    asset: Effect
    milestones: List[Milestone]
    title: str
    description: str


@dataclass(frozen=True)
class PatronIcon:
    path: str | None
    name: str | None
    image: WandImageProto | None


@dataclass(frozen=True)
class PatronPortraits:
    """Store the ingame path and name of all the patron portraits."""

    big: PatronIcon
    small: PatronIcon
    background: PatronIcon


@dataclass(frozen=True)
class ExaltationEffect:
    """
    This is the exaltation effect when this patron becomes the top global,
    usually activated when reaching 7K devotion. Only a single patron can have
    it.
    """

    asset: Effect
    title: str
    description: str


@dataclass(frozen=True)
class VenerationEffect:
    """
    This is the veneration effect when this patron reaches 4K global
    devotion. Can be activated by multiple patrons.
    """

    asset: Effect
    """The referenced effect asset, obtained from 'Wonder' path. The icon can be
    extracted from it as it is the same as 'WonderIcon' path."""
    title: str
    """The title of this effect."""
    description: str
    """The 'WonderDescription' text."""


@dataclass(frozen=True)
class ShrineEffect:
    """
    This is the simplest effect when this patron reaches 1K global
    devotion.
    """

    guid: int
    name: str
    """Ingame localized name."""
    shrines: List[MiniInstitutionBuilding]
    """List of shrines assets that belongs to the referenced 'AssetPoolNamed' from 'Shrine' path."""


class Patron(Asset, template_names="Patron"):
    """Specialized Asset for Patron (Deities) with pre-computed data."""

    @cached_property
    def portraits(self) -> PatronPortraits:
        """Maps the 'Portrait' prefixed paths into a dataclass."""

        def _make_icon(key: str) -> PatronIcon:
            val = cast("Path | None", self.find_value(key))
            icon_node = cast("FileNameAttribute | None", self.find(key))

            path_str = str(val) if val is not None else None
            img_obj = (
                icon_node.get_image()
                if isinstance(icon_node, FileNameAttribute)
                and icon_node.is_image
                and path_str
                and Path(path_str).exists()
                else None
            )

            return PatronIcon(path=path_str, name=val.stem if val is not None else None, image=img_obj)

        return PatronPortraits(
            big=_make_icon("Patron.PortraitBig"),
            small=_make_icon("Patron.PortraitSmall"),
            background=_make_icon("Patron.PortraitBackground"),
        )

    @cached_property
    def local_effects(self) -> List[LocalEffect]:
        """
        Maps the local effects into localized title and descriptions along with
        all the milestones and the referenced 'Effect' asset.
        """
        parsed_effects: List[LocalEffect] = []

        # TODO: For the first local effect description, we must build the list
        # of chains or units affected.
        for effect_item in cast("ListAttribute", self.find("Patron.LocalEffects")):
            effect_asset = cast("Effect", effect_item.find_ref("GUID"))

            milestones: List[Milestone] = [
                Milestone(
                    devotion=cast("int", mil.find_value("Devotion") or 0),
                    buff_scaling=cast("int", mil.find_value("BuffScaling") or 0),
                )
                for mil in cast("ListAttribute", effect_item.find("Milestones"))
            ]

            title_text = cast("Text | None", effect_item.find_value("Title"))
            desc_text = cast("Text | None", effect_item.find_value("Description"))

            parsed_effects.append(
                LocalEffect(
                    asset=effect_asset,
                    milestones=milestones,
                    title=title_text() if title_text else "No Title",
                    description=desc_text() if desc_text else "No Description",
                )
            )

        return parsed_effects

    @cached_property
    def exaltation_effects(self) -> List[ExaltationEffect]:
        """
        Maps the 'DominantEffects' list into localized title and description
        along with the referenced 'Effect' asset. This is the ingame exaltation
        effect.
        """
        parsed_effects: List[ExaltationEffect] = []

        for effect_item in cast("ListAttribute", self.find("Patron.DominantEffects")):
            effect_asset = cast("Effect", effect_item.find_ref("GUID"))

            title_text = cast("Text | None", effect_item.find_value("Title"))
            desc_text = cast("Text | None", effect_item.find_value("Description"))
            parsed_effects.append(
                ExaltationEffect(
                    asset=effect_asset,
                    title=title_text() if title_text else "No Title",
                    description=desc_text() if desc_text else "No Description",
                )
            )

        return parsed_effects

    @cached_property
    def veneration_effect(self) -> VenerationEffect:
        """
        Maps the 'Wonder' list into localized title and description along with
        the referenced 'Effect' asset. This is the ingame veneration effect.
        """
        wonder_effect = cast("Effect", self.find_value("Patron.Wonder"))
        wonder_desc_text = cast("Text | None", self.find_value("Patron.WonderDescription"))

        title_text = wonder_effect.text

        return VenerationEffect(
            asset=wonder_effect,
            title=title_text() if title_text else "No Title",
            description=wonder_desc_text() if wonder_desc_text else "No Description",
        )

    @cached_property
    def shrine_effect(self) -> ShrineEffect:
        """
        Maps the 'Shrine' AssetPoolBase path into a single effect that
        contains the list of shrines 'MiniInstitutionBuilding' assets (usually
        Roman and Celtic region).
        """
        shrines_list: List[MiniInstitutionBuilding] = []

        shrine_asset = cast("AssetPoolBase", self.find_ref("Patron.Shrine"))
        shrine_buildings = shrine_asset.asset_pool_list

        for building in cast("List[MiniInstitutionBuilding]", shrine_buildings):
            shrines_list.append(building)

        return ShrineEffect(guid=shrine_asset.guid, name=shrine_asset.name, shrines=shrines_list)
