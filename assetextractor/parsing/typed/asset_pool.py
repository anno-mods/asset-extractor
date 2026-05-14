from __future__ import annotations

from assetextractor.parsing.typed.asset_pool_base import AssetPoolBase


class AssetPool(AssetPoolBase, template_names="AssetPool"):
    """Specialized Asset for 'AssetPool' with pre-computed data."""

    @property
    def asset_list_path(self) -> str:
        return "AssetPool.AssetList"
