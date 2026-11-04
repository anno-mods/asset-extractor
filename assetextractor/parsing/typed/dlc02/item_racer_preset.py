from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, cast

from assetextractor.parsing.core.assets import Asset

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


@dataclass(frozen=True)
class ItemRacerAttribute:
    min_initial_value: int
    max_initial_value: int
    min_added_potential: int
    max_added_potential: int


@dataclass(frozen=True)
class ItemRacerAttributeOverwrite:
    """The processed 'ItemRacerAttributeOverwrite' properties as one single object."""

    speed: ItemRacerAttribute
    stamina: ItemRacerAttribute
    boost: ItemRacerAttribute
    consistency: ItemRacerAttribute


@dataclass(frozen=True)
class ItemRacerPresetInfo:
    """The processed 'ItemRacerPreset' properties as one single object."""

    racer_attribute_overwrites: ItemRacerAttributeOverwrite
    """The localized preset name. Comes from 'ItemRacerPreset.RacerAttributeOverwrites'."""

    min_additional_training_levels: int
    """The minimum additional training levels. Comes from 'ItemRacerPreset.MinAdditionalTrainingLevels'."""

    max_additional_training_levels: int
    """The maximum additional training levels. Comes from 'ItemRacerPreset.MaxAdditionalTrainingLevels'."""

    additional_training_increase_chances: list[str]
    """The list of additional training increase chances. Comes from 'ItemRacerPreset.AdditionalTrainingIncreaseChances'."""


class ItemRacerPreset(Asset, template_names="ItemRacerPreset"):
    """Specialized Asset for 'ItemRacerPreset' with pre-computed data."""

    @cached_property
    def racer_attribute_overwrites(self) -> ItemRacerAttributeOverwrite:
        """The structured 'RacerAttributeOverwrites' (property) data."""
        raw_overwrites = self.find("ItemRacerPreset.RacerAttributeOverwrites")

        if raw_overwrites is None:
            raise ValueError(f"Missing 'RacerAttributeOverwrites' for ItemRacerPreset '{self.name}'")

        fields = {"speed": "Speed", "stamina": "Stamina", "boost": "Boost", "consistency": "Consistency"}

        attribute_keys = ("MinInitialValue", "MaxInitialValue", "MinAddedPotential", "MaxAddedPotential")

        stats: dict[str, ItemRacerAttribute] = {}
        for attribute_name, stat_name in fields.items():
            stat_values = ItemRacerAttribute(
                min_initial_value=cast("int", raw_overwrites.find_value(f"{stat_name}.{attribute_keys[0]}")),
                max_initial_value=cast("int", raw_overwrites.find_value(f"{stat_name}.{attribute_keys[1]}")),
                min_added_potential=cast("int", raw_overwrites.find_value(f"{stat_name}.{attribute_keys[2]}")),
                max_added_potential=cast("int", raw_overwrites.find_value(f"{stat_name}.{attribute_keys[3]}")),
            )
            stats[attribute_name] = stat_values

        return ItemRacerAttributeOverwrite(**stats)

    @cached_property
    def racer_preset_info(self) -> ItemRacerPresetInfo:
        """The structured 'ItemRacerPreset' (property) data."""
        raw_training_chances = cast(
            "ListAttribute", self.find_value("ItemRacerPreset.AdditionalTrainingIncreaseChances")
        )
        training_chances = (
            [cast("str", chance.find_value("AdditionalIncreaseChance")) for chance in raw_training_chances]
            if raw_training_chances
            else []
        )

        min_atl = cast("int", self.find_value("ItemRacerPreset.MinAdditionalTrainingLevels"))
        max_atl = cast("int", self.find_value("ItemRacerPreset.MaxAdditionalTrainingLevels"))

        return ItemRacerPresetInfo(
            racer_attribute_overwrites=self.racer_attribute_overwrites,
            min_additional_training_levels=min_atl,
            max_additional_training_levels=max_atl,
            additional_training_increase_chances=training_chances,
        )
