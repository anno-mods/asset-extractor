from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, cast

from assetextractor.conversion.statistics.boost_conditions import BoostConditionParser
from assetextractor.parsing.core.attributes import ListAttribute
from assetextractor.parsing.typed.buffs import BUFF_CLASSES, BuffKey
from assetextractor.parsing.typed.common.effect_base import AssetWithEffect
from assetextractor.parsing.typed.common.enums import (
    ItemAllocation,
    ItemOrigin,
    NicheVisualization,
    RarityVisualization,
)

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import WandImageProto
    from assetextractor.parsing.core.texts import Text
    from assetextractor.parsing.typed.dlc02.item_racer_preset import ItemRacerPreset
    from assetextractor.parsing.typed.effect import Effect


@dataclass(frozen=True)
class ItemStandardInfo:
    """The processed 'Standard' properties as one single object."""

    std_name: str
    """The original asset name. Comes from the parent class 'name' property."""
    title: str
    """The localized asset name. Comes from the parent class 'text' property."""
    description: str
    """The localized asset description. Comes from 'Standard.InfoDescription'."""
    icon: WandImageProto | None


@dataclass(frozen=True)
class ItemBoostInfo:
    """The structured 'ItemWithBoost' properties as one single object."""

    boost_condition: str
    """The parsed boost condition text."""

    boost_hint: str
    """The localized boost hint text. Comes from 'ItemWithBoost.BoostHint'."""

    boost_buffs: list[BuffKey]
    """List of boost buffs applied to the targets. Comes from 'ItemWithBoost.BoostBuffs'."""


@dataclass(frozen=True)
class ItemInfo:
    """The processed 'Item' properties as one single object."""

    allocation: ItemAllocation
    """Specific item allocation type from dataset 'ItemAllocation'. Comes from
    'Item.Allocation'."""

    rarity: RarityVisualization
    """Specific item rarity type from dataset 'RarityVisualization'. Comes from
    'Item.Rarity'."""

    niche: NicheVisualization
    """Specific item rarity type from dataset 'NicheVisualization'. Comes from
    'Item.Niche'."""

    trade_price: int

    origin: ItemOrigin
    """Specific item origin type from dataset 'ItemOrigin'. Comes from
    'Item.Origin'."""

    needed_prestige: int
    """Prestige required to unlock this specialist. Usually applies to the
    Mythic ones and defaults to zero. Comes from 'Item.NeededPrestige'."""

    race_track_config: ItemRacerPreset | None
    """The race track configuration for this specialist. Comes from 'Item.RaceTrackConfig'."""

    mythic_effect: Effect | None
    """New mythic effect that applies for a few specialists. Comes from 'Item.MythicEffect'."""

    is_hero_racer: bool
    """Flag to notify if a specialist is a heroic racer (no idea what it does atm). Comes from 'Item.IsHeroRacer'."""


class Item(AssetWithEffect, template_names="Item"):
    """
    Specialized Asset for 'ItemWithBoost' (Specialists) with
    pre-computed data.
    """

    @cached_property
    def item_standard_info(self) -> ItemStandardInfo:
        """The structured 'Standard' (property) data."""
        desc_text = cast("Text | None", self.find_value("Standard.InfoDescription"))
        icon_node = self.icon

        return ItemStandardInfo(
            std_name=self.name,
            title=self.text() if self.text else "No title",
            description=desc_text() if desc_text else "No Description",
            icon=icon_node.get_image() if icon_node else None,
        )

    @cached_property
    def item_info(self) -> ItemInfo:
        """The structured 'Item' (property) data."""
        # Get the literal of allocation, rarity and niche.
        allocation_text = cast("ItemAllocation | None", self.find_value("Item.Allocation"))
        rarity_text = cast("RarityVisualization | None", self.find_value("Item.Rarity"))
        niche_text = cast("NicheVisualization | None", self.find_value("Item.Niche"))

        # Get the other properties.
        trade_value = cast("int | None", self.find_value("Item.TradePrice")) or 0
        origin_text = cast("ItemOrigin | None", self.find_value("Item.Origin"))

        # Get the new race and mythic effects, as example: Brother Brauda, Bread Bravura (GUID: 160522)
        mythic_eff = cast("Effect | None", self.find_ref("Item.MythicEffect"))
        is_hero_racer = cast("bool | None", self.find_value("Item.IsHeroRacer")) or False
        need_prestige = cast("int | None", self.find_value("Item.NeededPrestige")) or 0

        # Racer track configuration, if any. Comes from 'Item.RaceTrackConfig'.
        race_track_config = cast("ItemRacerPreset | None", self.find_ref("Item.RaceTrackConfig.ItemRacerPreset"))

        return ItemInfo(
            allocation=allocation_text or ItemAllocation.VILLA,
            rarity=rarity_text or RarityVisualization.COMMON,
            niche=niche_text or NicheVisualization.NONE,
            trade_price=trade_value,
            origin=origin_text or ItemOrigin.BASE_RELEASE,
            mythic_effect=mythic_eff,
            is_hero_racer=is_hero_racer,
            needed_prestige=need_prestige,
            race_track_config=race_track_config,
        )

    def print_racer_info(self, prefix: str = "") -> None:
        """Prints the racer track configuration, mythic effect, and hero racer status in a tree-style format."""
        i_info = self.item_info
        if i_info.race_track_config:
            racer_preset_info = i_info.race_track_config.racer_preset_info

            print(f"{prefix} Racer Preset:      {i_info.race_track_config.name}")
            print(f"{prefix} Min Training Lvls:            {racer_preset_info.min_additional_training_levels}")
            print(f"{prefix} Max Training Lvls:            {racer_preset_info.max_additional_training_levels}")

            print(f"{prefix} Additional Training Increase Chances:")
            for chance in racer_preset_info.additional_training_increase_chances:
                print(f"{prefix}   - {chance}")

            attributes = {
                "Speed": racer_preset_info.racer_attribute_overwrites.speed,
                "Stamina": racer_preset_info.racer_attribute_overwrites.stamina,
                "Boost": racer_preset_info.racer_attribute_overwrites.boost,
                "Consistency": racer_preset_info.racer_attribute_overwrites.consistency,
            }

            for attribute_name, attribute_values in attributes.items():
                print(f"{prefix} {attribute_name}:")
                print(f"{prefix}   Min Initial Value:      {attribute_values.min_initial_value}")
                print(f"{prefix}   Max Initial Value:      {attribute_values.max_initial_value}")
                print(f"{prefix}   Min Added Potential:    {attribute_values.min_added_potential}")
                print(f"{prefix}   Max Added Potential:    {attribute_values.max_added_potential}")
        else:
            print(f"{prefix} Racer Preset:      None")

        if i_info.mythic_effect:
            print(f"{prefix} Mythic Effect:     {i_info.mythic_effect.name}")
        if i_info.is_hero_racer:
            print(f"{prefix} Hero Racer:        {i_info.is_hero_racer}")


class ItemWithBoost(Item, template_names="ItemWithBoost"):
    """
    Specialized Asset for 'ItemWithBoost' (Specialists with extra perks) with
    pre-computed data. These shared all the properties of a normal 'Item' but
    have an additional config called 'ItemWithBoost' where boost conditions are
    stored.
    """

    @cached_property
    def boost_info(self) -> ItemBoostInfo:
        """The structured 'ItemWithBoost' data."""
        # Parse the condition using the parser
        parser = BoostConditionParser(self.cache, self.cache.texts)
        condition_str = parser.parse(self)

        # Extract boost hint text if available
        hint_text = cast("Text | None", self.find_value("ItemWithBoost.BoostHint"))

        # Extract boost buffs
        boost_buffs: list[BuffKey] = []
        boost_buffs_attr = self.find("ItemWithBoost.BoostBuffs")
        if isinstance(boost_buffs_attr, ListAttribute):
            for entry in boost_buffs_attr:
                buff = entry.find_ref("GUID")
                if isinstance(buff, BUFF_CLASSES):
                    boost_buffs.append(buff)

        return ItemBoostInfo(
            boost_condition=condition_str, boost_hint=hint_text() if hint_text else "No hint", boost_buffs=boost_buffs
        )

    def print_boost_info(self, prefix: str = "") -> None:
        """Prints the boost condition, hint, and boost buffs in a tree-style format."""
        b_info = self.boost_info
        print(f"{prefix}Boost Condition: {b_info.boost_condition}")
        if b_info.boost_hint and b_info.boost_hint != "No hint":
            print(f"{prefix}Boost Hint:      {b_info.boost_hint}")
        self.print_buffs(b_info.boost_buffs, prefix=prefix)
