from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, List

from assetextractor.parsing.core.asset_factories.effect import Effect
from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.core.attributes import ListAttribute, PrimitiveAttribute, ReferenceAttribute

# Import AssetCache ONLY for type checking
if TYPE_CHECKING:
    import lxml.etree as et

    from assetextractor.parsing.core.assets import AssetCache
    from assetextractor.parsing.core.common import NamedElement
    from assetextractor.parsing.core.texts import Text


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


class Patron(Asset):
    """Specialized Asset for Patron (Deities) with pre-computed data."""

    def __init__(self, node: et._Element, cache: AssetCache):
        super().__init__(node, cache)

    def _get_text_from_node(self, elm: NamedElement[Any], path: str, fallback: str) -> str:
        """Helper to resolve a Text node path into a localized string."""
        node = elm.find(path)

        if node is not None:
            lang = self.cache.texts.converter.language
            text_attr: Text | None = node()
            if text_attr is not None:
                # Return the localized string, fallback to English, then to the provided default
                return text_attr.get(lang) or text_attr.get("english") or fallback  # type: ignore

        return fallback

    @cached_property
    def local_effects(self) -> List[LocalEffect]:
        """
        Maps the local effects into localized title and descriptions along
        with all the milestones.
        """
        local_effects_list = self.find("Patron.LocalEffects")
        if not isinstance(local_effects_list, ListAttribute):
            return []

        parsed_effects: List[LocalEffect] = []

        for effect_item in local_effects_list:
            # Assign the asset that references this GUID.
            effect_ref = effect_item.find("GUID")
            milestones = effect_item.find("Milestones")

            out_milestones: List[Milestone] = []
            effect_asset: Effect | None = None

            if isinstance(effect_ref, ReferenceAttribute):
                # Specialize the "LocalEffect" -> "GUID" referenced asset to "Effect".
                effect_node = self.cache.get(effect_ref.guid)
                if isinstance(effect_node, Asset):
                    effect_asset = Effect(effect_node.node, self.cache)

            if isinstance(milestones, ListAttribute):
                for i, mil in enumerate(milestones):  # type: ignore
                    d_node = mil.find("Devotion")
                    s_node = mil.find("BuffScaling")
                    devotion_val = (
                        d_node.value if isinstance(d_node, PrimitiveAttribute) and isinstance(d_node.value, int) else 0
                    )
                    scaling_val = (
                        s_node.value if isinstance(s_node, PrimitiveAttribute) and isinstance(s_node.value, int) else 0
                    )

                    # print(f"  Milestone {i} - Devotion {devotion_val} - Buff Scaling {scaling_val}")

                    out_milestones.append(Milestone(devotion=devotion_val, buff_scaling=scaling_val))

            title_val = self._get_text_from_node(effect_item, "Title", "No Title")
            desc_val = self._get_text_from_node(effect_item, "Description", "No Title")

            # Asign the required effect data to the list.
            parsed_effects.append(
                LocalEffect(asset=effect_asset, milestones=out_milestones, title=title_val, description=desc_val)
            )

        return parsed_effects
