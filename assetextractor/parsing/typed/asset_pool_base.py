from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, List, cast

from assetextractor.parsing.core.assets import Asset

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


class AssetPoolBase(Asset):
    """Common logic for all AssetPool types."""

    @property
    def asset_list_path(self) -> str:
        """Subclasses must override this with their specific XML path."""
        raise NotImplementedError

    @cached_property
    def asset_pool_list(self) -> List[Asset]:
        out: List[Asset] = []
        for entry in cast("ListAttribute", self.find(self.asset_list_path)):
            asset = entry.find_ref("Asset")
            if asset is not None:
                out.append(asset)
        return out
