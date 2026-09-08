from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List, Union, cast

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.texts import strip_html_tags
from assetextractor.parsing.typed.common.enums import BuildingType, Region
from assetextractor.parsing.typed.construction_category import ConstructionCategory
from assetextractor.parsing.typed.ownership import UplayProduct

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute
    from assetextractor.parsing.core.texts import Text
    from assetextractor.parsing.typed.effect import Effect


OriginHintType = Union[UplayProduct, ConstructionCategory]


@dataclass(frozen=True)
class Building:
    type: BuildingType
    """Specificy building type from dataset 'BuildingType'. Comes from 'Building.BuildingType'."""
    category_name: str
    """Localized category name. Comes from 'Building.BuildingCategoryName'."""
    associated_regions: List[Region]
    """The associated ingame region that this building can be used on."""
    origin_hint: OriginHintType | None
    """The asset that unlocks this building. If None, means this
    building is unlocked by default in the base game."""
    func_effects: List[Effect]
    """The list of 'Effect' assets applied to this building, otherwise empty."""


class AssetWithBuilding(Asset):
    """Base class for assets that contain a 'Building' object."""

    @cached_property
    def origin_hint_ui(self) -> str:
        """
        Format the origin hint from the localized asset text. This can be 'Hall
        of Fame', 'Prophecies of Ash', etc.If not defined, set to 'Base' as
        default.
        """
        hint_asset = self.building_info.origin_hint

        if hint_asset and hint_asset.text:
            raw_text = hint_asset.text()
            return strip_html_tags(raw_text)

        return "Base"

    @cached_property
    def building_info(self) -> Building:
        raw_building_type = self.find_value("Building.BuildingType")
        building_type = cast("BuildingType", raw_building_type) if raw_building_type else BuildingType.OTHER

        raw_cat_name = cast("Text | None", self.find_value("Building.BuildingCategoryName"))
        cat_name = raw_cat_name() if raw_cat_name else "N/A"

        raw_regions = cast("List[Region] | None", self.find_value("Building.AssociatedRegions"))
        regions = raw_regions if raw_regions else []

        # Get the asset 'UplayProduct' or 'ConstructionCategory' that unlocks this building (if applies).
        origin_hint = cast("OriginHintType | None", self.find_ref("Building.OriginHint"))

        # Get the asset list of functional effects.
        func_effects_list = cast("ListAttribute | None", self.find_value("Building.FunctionalEffects"))
        func_effects: List[Effect] = []
        if func_effects_list:
            for item in func_effects_list:
                item_fun_effect = cast("Effect", item.find_ref("FunctionalEffect"))
                func_effects.append(item_fun_effect)

        return Building(
            type=building_type,
            category_name=cat_name,
            associated_regions=regions,
            origin_hint=origin_hint,
            func_effects=func_effects,
        )

        # if self.assets.properties.ui_text_cache and isinstance(source_cat_attr, Attribute):
        #     source_cat_literal = source_cat_attr()
        #     if not isinstance(source_cat_literal, str):
        #         pass

        #     ui_cache = self.assets.properties.ui_text_cache
        #     source_cat_mapping = ui_cache.get_ui_text("BuffCategoryType", source_cat_literal)
        #     if source_cat_mapping is not None and source_cat_mapping.text is not None:
        #         source_cat_localized = source_cat_mapping.text()
        #     else:
        #         source_cat_localized = source_cat_literal

        #     print(f"Source Category: {source_cat_localized}")
