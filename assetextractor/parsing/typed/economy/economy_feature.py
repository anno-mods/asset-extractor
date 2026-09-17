from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Dict, List, TypedDict, cast

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.typed.common.enums import NoMetaRegion, Region

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute, ListItem
    from assetextractor.parsing.typed.economy.city_status import CityStatus


@dataclass(frozen=True)
class CityStatusListItemInfo:
    """A single entry in the CityStatusFeature's region mapping."""

    required_population: int
    """The required population count for this city-status level."""

    city_status: CityStatus
    """Asset reference to the CityStatus level for this entry."""


@dataclass(frozen=True)
class CityStatusFeatureInfo:
    """The processed 'CityStatusFeature' properties as one single object."""

    region: Dict[NoMetaRegion, List[CityStatusListItemInfo]]


class CityStatusList(TypedDict):
    CityStatusList: ListAttribute


class EconomyFeature(Asset, template_names="EconomyFeature"):
    """Specialized Asset for 'EconomyFeature' with pre-computed data."""

    @cached_property
    def city_status_feature_info(self) -> CityStatusFeatureInfo:
        """Return the processed 'CityStatusFeature' data for this asset."""
        region_mapping: dict[NoMetaRegion, List[CityStatusListItemInfo]] = {}
        regions = cast("Dict[Region, CityStatusList]", self.find_value("EconomyFeature7.CityStatusFeature.Region"))

        city_status_lists: dict[NoMetaRegion, ListAttribute] = {
            Region.ROMAN: regions[Region.ROMAN].get("CityStatusList"),
            Region.CELTIC: regions[Region.CELTIC].get("CityStatusList"),
            Region.EGYPTIAN: regions[Region.EGYPTIAN].get("CityStatusList"),
        }

        for region_key, city_sl in city_status_lists.items():
            region_mapping[region_key] = []

            for entry in city_sl:
                city_status = cast("CityStatus | None", entry.find_ref("CityStatus"))
                if city_status is None:
                    continue

                required_pop = cast("ListAttribute | None", entry.find("RequiredPopulation"))
                required_pop_count = 0

                if required_pop is not None and len(required_pop) > 0:
                    single_rp = cast("ListItem", required_pop[0])
                    pop_count = cast("int | None", single_rp.find_value("PopulationCount"))
                    required_pop_count = int(pop_count) if pop_count is not None else 0

                city_status_info = CityStatusListItemInfo(
                    required_population=required_pop_count, city_status=city_status
                )
                region_mapping[region_key].append(city_status_info)

        return CityStatusFeatureInfo(region=region_mapping)
