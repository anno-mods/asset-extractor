#!/usr/bin/env python3
"""
Dynamic extraction script for Anno RDA files using RDAConsole.exe.

This script extracts:
- All files from config.rda
- All files with paths containing "icon" from ui.rda
- All *.ifo files from all graphics_*.rda files

Usage:
    python extract.py [config_path]
"""

import subprocess
import sys
from pathlib import Path
from typing import List, TypedDict

from assetextractor.extraction.utils import Config


class RDAFileGroups(TypedDict):
    config: list[Path]
    ui: list[Path]
    graphics: list[Path]
    patches: list[Path]


class RDAExtractor:
    """Handles extraction of RDA files using RDAConsole.exe."""

    def __init__(self, config: Config):
        self.config = config
        self.rda_console_path = Path("./RDAConsole/RDAConsole.exe").resolve()
        self.main_data_path = self.config.game_path / "maindata"

        # Ensure cache directory exists
        self.config.cache_path.mkdir(parents=True, exist_ok=True)

    def check_rda_console(self) -> bool:
        """Check if RDAConsole.exe is available and working."""
        if not self.rda_console_path.exists():
            print(f"Error: RDAConsole.exe not found at {self.rda_console_path}")
            print("Please ensure RDAConsole is installed in the repository root.")
            return False

        try:
            subprocess.run([str(self.rda_console_path)], capture_output=True, text=True, timeout=10)
            return True
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            print(f"Error testing RDAConsole: {e}")
            return False

    def find_rda_files(self) -> RDAFileGroups:
        """Find all relevant RDA files in main data directory."""
        if not self.main_data_path.exists():
            print(f"Error: Main data directory not found at {self.main_data_path}")
            return {key: [] for key in RDAFileGroups.__annotations__}  # type: ignore

        rda_files: RDAFileGroups = {"config": [], "ui": [], "graphics": [], "patches": []}

        for rda_file in self.main_data_path.glob("*.rda"):
            name = rda_file.stem.lower()
            if name == "config" or name == "data33":  # data33 is last rda file of Anno 1800
                rda_files["config"].append(rda_file)
            elif name == "ui":
                rda_files["ui"].append(rda_file)
            elif name.startswith("graphics") or name == "shared_configs":
                rda_files["graphics"].append(rda_file)
            # Patch files do contain UI (icons) folders.
            elif name.startswith("zz_patchfiles"):
                rda_files["patches"].append(rda_file)

        return rda_files

    def run_rda_console(self, args: List[str]) -> bool:
        """Execute RDAConsole with given arguments."""
        cmd = [str(self.rda_console_path), *args]
        print(f"Running: {' '.join(cmd)}")

        try:
            # Use shell=True and don't capture output to avoid console handle issues
            subprocess.run(
                cmd,
                check=True,
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0,
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"RDAConsole failed with exit code {e.returncode}")
            return False

    def extract_config_rda(self, rda_file: Path) -> bool:
        """Extract all files from config.rda."""
        print(f"\nExtracting all files from {rda_file.name}...")

        output_dir = self.config.cache_path
        args = [
            "extract",
            "-f",
            str(rda_file),
            "-y",  # Overwrite without prompting
            "-o",
            str(output_dir),
        ]

        return self.run_rda_console(args)

    def extract_ui_icons(self, rda_file: Path) -> bool:
        """Extract files containing 'icon' in path from ui.rda or any other .rda file that might contain icons."""
        print(f"\nExtracting icon files from {rda_file.name}...")

        output_dir = self.config.cache_path
        args = [
            "extract",
            "-f",  # Filename (can be multiple)
            str(rda_file),
            "-y",  # Overwrite without prompting
            "-o",  # Output path.
            str(output_dir),
            "--filter",
            r"^data/ui/.*\.dds$",  # Regex filter for .dds files inside "data/ui" dir.
        ]

        return self.run_rda_console(args)

    def extract_graphics_ifo(self, rda_file: Path) -> bool:
        """Extract *.ifo files from graphics RDA files."""
        print(f"\nExtracting .ifo files from {rda_file.name}...")

        output_dir = self.config.cache_path
        args = [
            "extract",
            "-f",
            str(rda_file),
            "-y",  # Overwrite without prompting
            "-o",
            str(output_dir),
            "--filter",
            r".*\.ifo$",  # Regex filter for .ifo files
        ]

        return self.run_rda_console(args)

    def extract_all(self) -> bool:
        """Run complete extraction process."""
        print("Starting RDA extraction process...")

        if not self.check_rda_console():
            return False

        rda_files = self.find_rda_files()

        if not any(rda_files.values()):
            print(f"No RDA files found in {self.main_data_path}")
            return False

        success = True

        # Extract config.rda files
        for config_rda in rda_files["config"]:
            if not self.extract_config_rda(config_rda):
                success = False

        # Extract icon files from ui.rda files
        for ui_rda in rda_files["ui"]:
            if not self.extract_ui_icons(ui_rda):
                success = False

        # Extract .ifo files from graphics RDA files
        for graphics_rda in rda_files["graphics"]:
            if not self.extract_graphics_ifo(graphics_rda):
                success = False

        # Extract icon files from patches RDA files
        for patch_rda in rda_files["patches"]:
            if not self.extract_ui_icons(patch_rda):
                success = False

        if success:
            print("\n✅ Extraction completed successfully!")
            print(f"Files extracted to: {self.config.cache_path}")
        else:
            print("\n❌ Some extractions failed. Check the output above.")

        return success


def main():
    """Main entry point."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"

    try:
        config = Config.from_json(config_path)
        extractor = RDAExtractor(config)
        success = extractor.extract_all()
        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
