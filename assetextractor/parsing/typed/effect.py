from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.typed.asset_pool_named import AssetPoolNamed
from assetextractor.parsing.core.assets import Asset

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


class Effect(Asset, template_names="Effect"):
    """Specialized Asset for Effect with pre-computed data."""

    @cached_property
    def buffs(self) -> List[Asset]:
        """Return a list of Assets that can be either 'BuildingBuff', 'ShipBuff' and so on."""
        allowed_template_names = {"BuildingBuff", "ShipBuff"}
        out: List[Asset] = []
        for entry in cast("ListAttribute", self.find("Effect.Buffs")):
            buff = entry.find_ref("GUID")
            if buff is not None and buff.template.name in allowed_template_names:
                out.append(buff)
        return out

    @cached_property
    def targets(self) -> List[AssetPoolNamed]:
        """Return the AssetPoolNamed targets whose members are affected by this effect."""
        out: List[AssetPoolNamed] = []
        for entry in cast("ListAttribute", self.find("Effect.Targets")):
            target = entry.find_ref("GUID")
            if isinstance(target, AssetPoolNamed):
                out.append(target)
        return out
