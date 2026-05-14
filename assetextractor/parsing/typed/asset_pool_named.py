from __future__ import annotations

from assetextractor.parsing.typed.asset_pool_base import AssetPoolBase


class AssetPoolNamed(AssetPoolBase, template_names="AssetPoolNamed"):
    """Specialized Asset for 'AssetPoolNamed' with pre-computed data."""

    @property
    def asset_list_path(self) -> str:
        return "AssetPool.AssetList"
