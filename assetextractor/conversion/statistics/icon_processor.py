from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple, TypedDict

from assetextractor.parsing.core.attributes import FileNameAttribute

if TYPE_CHECKING:
    from assetextractor.parsing.core.assets import Asset
    from assetextractor.parsing.core.attributes import WandImageProto


class IconData(TypedDict):
    name: str | None
    canon_name: str | None
    image: WandImageProto | None
    path: str | None
    """Original path."""
    image_url: str | None
    """Formatted path for web usage."""


class IconProcessor:
    """Handles icon metadata extraction, path sanitization, and batch exporting."""

    @staticmethod
    def clean_path(raw_path: str | None) -> str | None:
        """Removes the .cache prefix and file extension for web-ready URLs."""
        if not raw_path:
            return None

        _, sep, after = raw_path.partition(".cache")
        return str(Path(after).with_suffix("")) if sep else raw_path

    @classmethod
    def get_icon_package(cls, asset: Asset, include_image: bool = False) -> IconData:
        """Extracts and processes all icon-related metadata from an asset."""
        path_str = None
        name = None

        icon_node = asset.find("Standard.IconFilename")
        if icon_node and isinstance(icon_node, FileNameAttribute) and icon_node.value:
            path_str = str(icon_node.value)
            name = icon_node.value.stem

        img_obj: WandImageProto | None = None
        if include_image and asset.icon and path_str and Path(path_str).exists():
            img_obj = asset.icon.get_image()

        return {
            "name": name,
            "canon_name": asset.icon.canonical_name if asset.icon is not None else name,
            "image": img_obj,
            "path": path_str,
            "image_url": cls.clean_path(path_str),
        }

    @classmethod
    def export_icons(
        cls, assets: List[Asset], output_base: Path | str, quality: int = 80, resize: Tuple[int, int] | None = (64, 64)
    ) -> Dict[str, int]:
        """
        Batch processes icons from a list of assets, applies compression, and saves to a custom folder.

        Args:
            assets: List of Asset objects (like LandUnits or Patrons).
            output_base: Target directory (e.g., 'results/icons').
            quality: WebP compression quality (1-100).
            resize: Optional (width, height) tuple to downscale images.

        Returns:
            Dict[str, int]: Success/Skip/Error statistics.
        """
        base_dir = Path(output_base).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

        seen_paths: set[str] = set()
        stats: Dict[str, int] = {"exported": 0, "skipped": 0, "errors": 0}

        for asset in assets:
            # 1. Get the icon package which already computes the canonical_name
            icon_data = cls.get_icon_package(asset, include_image=True)
            original_path = icon_data["path"]
            img = icon_data["image"]
            # Use canonical_name if available, otherwise fallback to asset name
            file_name = icon_data["canon_name"] or asset.name

            if not original_path or original_path in seen_paths or img is None:
                stats["skipped"] += 1
                continue

            seen_paths.add(original_path)

            # --- THE FIX: FLATTENED PATH USING CANONICAL NAME ---
            # We ignore the directory structure and save directly to base_dir
            target_file = (base_dir / f"{file_name}").with_suffix(".webp")
            # ----------------------------------------------------

            try:
                img.format = "webp"
                img.compression_quality = quality

                if resize:
                    img.resize(resize[0], resize[1])

                # Save to the flattened path
                img.save(filename=str(target_file))  # type: ignore

                stats["exported"] += 1
                # Print relative to 'results' (two levels up from the file)
                # This results in: [OK] PatronMars -> results/icons/patrons/icon_2d_deity_mars_0.webp
                print(f"  [OK] {asset.name} -> {target_file.relative_to(base_dir.parent.parent.parent)}")

            except Exception as e:
                print(f"  [ERROR] Failed to save {asset.name}: {e}")
                stats["errors"] += 1

        print("---")
        print(f"Finished! Exported: {stats['exported']} | Skipped: {stats['skipped']}")
        return stats
