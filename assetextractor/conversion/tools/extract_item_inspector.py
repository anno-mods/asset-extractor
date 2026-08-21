"""Self-contained script to populate the Anno 117 Item Inspector's data folder.

The Item Inspector (https://github.com/Taludas/Anno-117-Item-Inspector) ships its own
copy of assets.xml and the loca text files under data/base/config/, and resolves each
item's icon at runtime via its literal ``Standard.IconFilename`` path (e.g.
"data/ui/fhd/base/icon_content/items_specialist/unique/icon_3d_specialist_hooded_01.png").

Running this script overwrites assets.xml and texts_*.xml from the source cache (cheap,
must always reflect the exact source data), then converts each Item's icon from its
extracted .dds source to .png at the exact mirrored path the Item Inspector expects --
instead of bulk-copying the entire icon set (thousands of files, most never shown by
that app). Icons are only added if missing, unless --force is passed.

Usage:
    uv run python -m assetextractor.conversion.tools.extract_item_inspector
    uv run python -m assetextractor.conversion.tools.extract_item_inspector --force
"""

import argparse
import shutil
from pathlib import Path

from assetextractor.extraction.utils import Config
from assetextractor.parsing.core.assets import AssetCache
from assetextractor.parsing.core.attributes import FileNameAttribute

DEFAULT_TARGET = r"..\Anno-117-Item-Inspector"

# Relative to both the source cache_path and the target's data/ folder.
ASSETS_XML_REL = Path("data/base/config/export/assets.xml")
LOCA_DIR_REL = Path("data/base/config/gui")


def copy_config_files(cache_path: Path, target_root: Path) -> None:
    """Overwrites assets.xml and the loca text files from the source cache.

    Unlike icons (only added if missing), these are cheap and must always
    reflect the exact source data, so they are unconditionally overwritten.
    """
    src_assets_xml = cache_path / ASSETS_XML_REL
    if not src_assets_xml.exists():
        raise FileNotFoundError(f"{src_assets_xml} not found -- run extraction first")

    dest_assets_xml = target_root / ASSETS_XML_REL
    dest_assets_xml.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_assets_xml, dest_assets_xml)
    print(f"  [OK] {ASSETS_XML_REL}")

    src_loca_dir = cache_path / LOCA_DIR_REL
    dest_loca_dir = target_root / LOCA_DIR_REL
    dest_loca_dir.mkdir(parents=True, exist_ok=True)
    for src_text in sorted(src_loca_dir.glob("texts_*.xml")):
        shutil.copyfile(src_text, dest_loca_dir / src_text.name)
    print(f"  [OK] {LOCA_DIR_REL}/texts_*.xml")


# Matches the Item Inspector's own display resolution (get_icon_image size=(128, 128)
# in anno117_item_inspector.py) -- the source .dds files are much larger (e.g. 512x512),
# so resizing here keeps the exported data folder close to its previous size.
ICON_SIZE = (128, 128)


def convert_icon(icon: FileNameAttribute, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = icon.get_image()
        if img is None:
            return False
        img.format = "png"
        img.resize(*ICON_SIZE)
        img.strip()  # type: ignore # drop ImageMagick metadata (e.g. date:create) for reproducible output
        img.save(filename=str(dest))  # type: ignore
        return True
    except Exception as e:
        print(f"  [ERROR] {icon.value} -> {dest}: {e}")
        return False


def populate_item_icons(assets: AssetCache, target_root: Path, force: bool) -> dict[str, int]:
    stats = {"converted": 0, "skipped_existing": 0, "missing_source": 0, "errors": 0, "no_icon": 0}
    seen: set[str] = set()

    item_template = assets.templates["Item"]
    if item_template is None:
        raise RuntimeError("Template 'Item' not found in AssetCache")

    for item in item_template.assets:
        icon = item.icon
        if icon is None or icon.value is None:
            stats["no_icon"] += 1
            continue

        rel_path = icon.identifier
        if rel_path in seen:
            continue
        seen.add(rel_path)

        dest = target_root / rel_path
        if dest.exists() and not force:
            stats["skipped_existing"] += 1
            continue

        if not icon.value.exists():
            print(f"  [MISSING] {rel_path} -> no extracted source at {icon.value}")
            stats["missing_source"] += 1
            continue

        if convert_icon(icon, dest):
            stats["converted"] += 1
        else:
            stats["errors"] += 1

    stats["unique_icons"] = len(seen)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.json", help="Config json to read the source cache_path from")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Item Inspector repo root (contains data/)")
    parser.add_argument("--force", action="store_true", help="Re-convert icons that already exist at destination")
    args = parser.parse_args()

    config = Config.from_json(args.config)
    target_root = Path(args.target)

    print("--- Config files ---")
    copy_config_files(config.cache_path, target_root)

    assets = AssetCache.load(config)
    stats = populate_item_icons(assets, target_root, args.force)

    print("\n--- Summary ---")
    for key, value in stats.items():
        print(f"{key}: {value}")

    if stats["missing_source"]:
        print(
            "\nSome icons were not found in the extracted cache. "
            "Run `uv run python -m assetextractor.extraction.extract` against the config used above and retry."
        )


if __name__ == "__main__":
    main()
