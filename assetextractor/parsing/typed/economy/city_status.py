from __future__ import annotations

from dataclasses import dataclass, fields
from functools import cached_property
from typing import TYPE_CHECKING, Iterator, cast

import pandas as pd

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.typed.common.enums import Region

if TYPE_CHECKING:
    from datetime import timedelta


_ATTRIBUTE_KEYS = (
    ("belief", "Belief.Value"),
    ("knowledge", "Knowledge.Value"),
    ("prestige", "Prestige.Value"),
    ("happiness", "Happiness.Value"),
    ("fire_safety", "FireSafety.Value"),
    ("health", "Health.Value"),
)


@dataclass(frozen=True)
class CityStatusAttributeEffects:
    """The processed CityStatus effect block for a single region preset."""

    belief: int
    knowledge: int
    prestige: int
    happiness: int
    fire_safety: int
    health: int


@dataclass(frozen=True)
class CityStatusIncidentIntervalInfo:
    """The processed 'CityStatus.IncidentInterval' incident interval information."""

    fire: timedelta | None
    unrest: timedelta | None
    disease: timedelta | None
    inferno: timedelta | None
    rebellion: timedelta | None
    plague: timedelta | None
    tremors: timedelta | None

    def _format_td(self, td: timedelta | None) -> str:
        """Internal helper to format a timedelta into HH:MM:SS using pandas."""
        if td is None:
            return "N/A"

        # Wrap the python timedelta in a pandas Timedelta
        p_td = pd.Timedelta(td)
        total_seconds = int(p_td.total_seconds())

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def iter_typed_fields(self) -> Iterator[tuple[str, str]]:
        """Yields (field_name, formatted_value) for each field."""
        for field in fields(self):
            value = getattr(self, field.name)
            formatted_value = self._format_td(value)
            yield field.name, formatted_value


@dataclass(frozen=True)
class CityStatusInfo:
    """The processed 'CityStatus' data that is exposed to the extractor."""

    guid: int
    name: str
    title: str
    region: Region
    incident_interval: CityStatusIncidentIntervalInfo
    attribute_effects_roman: dict[str, int]
    attribute_effects_regional: dict[str, int]
    attribute_effects_mixed: dict[str, int]


class CityStatus(Asset, template_names="CityStatus"):
    """Typed view for CityStatus assets, including region and effect summaries."""

    @cached_property
    def region(self) -> Region:
        value = (self.text() if self.text is not None else self.name or "").lower()
        if "celtic" in value:
            return Region.CELTIC
        if "roman" in value:
            return Region.ROMAN
        if "egyptian" in value:
            return Region.EGYPTIAN

        value = (self.name or "").lower()
        if "celtic" in value:
            return Region.CELTIC
        if "roman" in value:
            return Region.ROMAN
        if "egyptian" in value:
            return Region.EGYPTIAN

        raise ValueError(f"CityStatus region could not be resolved for asset {self.guid} ({self.name})")

    @cached_property
    def incident_interval_info(self) -> CityStatusIncidentIntervalInfo:
        """Return the processed 'CityStatus.IncidentInterval' information for this asset."""
        base_path = "CityStatus.IncidentInterval"

        return CityStatusIncidentIntervalInfo(
            fire=cast("timedelta | None", self.find_value(f"{base_path}.Fire.Interval")),
            unrest=cast("timedelta | None", self.find_value(f"{base_path}.Unrest.Interval")),
            disease=cast("timedelta | None", self.find_value(f"{base_path}.Disease.Interval")),
            inferno=cast("timedelta | None", self.find_value(f"{base_path}.Inferno.Interval")),
            rebellion=cast("timedelta | None", self.find_value(f"{base_path}.Rebellion.Interval")),
            plague=cast("timedelta | None", self.find_value(f"{base_path}.Plague.Interval")),
            tremors=cast("timedelta | None", self.find_value(f"{base_path}.Tremors.Interval")),
        )

    def _extract_effect_group(self, base_path: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for key, sub_path in _ATTRIBUTE_KEYS:
            value = self.find_value(f"{base_path}.{sub_path}")
            result[key] = int(value) if value is not None else 0
        return result

    @cached_property
    def city_status_info(self) -> CityStatusInfo:
        title = cast("str | None", self.find_value("CityStatus.CityStatusName"))
        region = self.region

        return CityStatusInfo(
            guid=self.guid,
            name=self.name,
            title=title if title else self.name or "",
            region=region,
            incident_interval=self.incident_interval_info,
            attribute_effects_roman=self._extract_effect_group("CityStatus.AttributeEffectsRoman"),
            attribute_effects_regional=self._extract_effect_group("CityStatus.AttributeEffectsRegional"),
            attribute_effects_mixed=self._extract_effect_group("CityStatus.AttributeEffectsMixed"),
        )
