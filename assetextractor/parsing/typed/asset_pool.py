from __future__ import annotations

from assetextractor.parsing.core.asset_factories.common.asset_pool_base import AssetPoolBase


class AssetPool(AssetPoolBase):
    """Specialized Asset for 'AssetPool' with pre-computed data."""

    @property
    def asset_list_path(self) -> str:
        return "AssetPool.AssetList"
