from pathlib import Path

from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.templates import Template
from assetextractor.extraction.utils import Config

import numpy as np
from lxml import etree as ET
import json

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

class Converter:
    def __init__(self, cache: AssetCache):
        self.assets = cache
        self.building_sizes: dict[int, tuple[int, int]] = {}

    @staticmethod
    def get_building_size_from_ifo(ifo_path: str | Path) -> tuple[int, int] | None:
        """
        Calculate building size from .ifo file by analyzing BuildBlocker corner positions.
        
        This parses the building blocker XML and extracts corner coordinates to calculate
        the footprint size, similar to the approach used in Anno 1800 mods.
        
        Args:
            ifo_path: Path to the .ifo file
            
        Returns:
            Tuple of (width, height) in grid cells, or None if calculation failed
        """
        try:
            ifo_tree = ET.parse(ifo_path)
            corners: list[list[float]] = []
            
            # Extract all corner positions from BuildBlocker elements
            for corner_elem in ifo_tree.findall(".//BuildBlocker/Position"):
                xf_elem = corner_elem.find("xf")
                zf_elem = corner_elem.find("zf")
                
                if xf_elem is not None and xf_elem.text and zf_elem is not None and zf_elem.text:
                    corners.append([
                        float(xf_elem.text),
                        float(zf_elem.text)
                    ])
            
            if len(corners) < 4:
                # Need at least 4 corners to define a rectangle
                return None
            
            # Convert to numpy array and transpose to separate x and z coordinates
            corners_array = np.array(corners).T  # Shape: (2, n_corners)
            
            # For buildings with multiple blockers (e.g., mines), use only the first blocker
            # which typically has 4 corners, skip the rest
            if len(corners_array[0]) >= 8:
                # Calculate diagonals to determine which blocker is the main one
                diag0 = np.linalg.norm(
                    np.max(corners_array[:, 0:4], axis=1) - 
                    np.min(corners_array[:, 0:4], axis=1)
                )
                diag1 = np.linalg.norm(
                    np.max(corners_array[:, 4:8], axis=1) - 
                    np.min(corners_array[:, 4:8], axis=1)
                )
                
                # Use the smaller blocker (typically 0.1 tolerance)
                if diag1 > diag0 + 0.1:
                    corners_array = corners_array[:, 0:4]
            
            # Calculate size as the difference between max and min coordinates
            # Round to nearest integer and reverse order (z, x) -> (width, height)
            size_raw = np.max(corners_array, axis=1) - np.min(corners_array, axis=1)
            size = np.array([int(round(val)) for val in size_raw])
            
            # Reverse order: return as [width, height] instead of [x, z]
            return tuple(size[::-1])
        
        except Exception as e:
            print(f"Error parsing IFO file {ifo_path}: {e}")
            return None


    @staticmethod
    def get_building_ifo_path(asset: Asset) -> Path | None:
        """
        Resolve the IFO file path for a building asset.
        
        The asset-extractor extracts .ifo files to a results directory based on the
        original game path structure.
        
        Args:
            asset: The building Asset object
            
        Returns:
            Path to the .ifo file, or None if not found
        """
        # Building IFO files are extracted to a graphics subdirectory
        # You may need to adjust this path based on your extraction setup
        # Check config.json for where files are extracted

        variations = asset.find("Object.Variations")
        if(variations is None or len(variations.value) == 0 or "Filename" not in variations.value[0]):
            polygonsPath = asset.find("Polygon.Path")
            if(polygonsPath is None):
                return None
            
            polygonsPath = polygonsPath()
            if str(polygonsPath).endswith("modules"):
                polygonsPath = Path(str(polygonsPath).removesuffix("modules"))
            
            polygonFiles = sorted(polygonsPath.glob("*.ifo"))
            for polygonFile in polygonFiles:
                return polygonFile
        
        return Path(str(variations.value[0].value["Filename"]).replace(".cfg", ".ifo").replace("Filename: ", ""))
    
    def process_assets(self, assets: list[Asset]) -> None:
        for asset in assets:
            if asset.name is None or "TEST" in asset.name:
                continue

            ifo_file = self.get_building_ifo_path(asset)
            building_size = self.get_building_size_from_ifo(ifo_file) if ifo_file is not None else None
            if building_size is not None:
                self.building_sizes[asset.guid] = building_size
            else:
                # This often happened for 1x1 buildings, such as fields and ornaments
                self.building_sizes[asset.guid] = (1, 1)
                print(f"Asset ID {asset.guid} ({asset.name}): Size could not be determined")

    def run(self):
        for template in self.assets.templates.groups["Objects"]["Buildings"]:
            if not isinstance(template, Template):
                for el in template.elements:
                    self.process_assets(template.elements[el].assets)
            else:
                self.process_assets(template.assets)

        with open("./building-sizes.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(self.building_sizes, ensure_ascii=False, indent=2, sort_keys=True, cls=NpEncoder))

if __name__ == "__main__":
    config = Config.from_json("config.json")
    cache = AssetCache.load(config)
    converter = Converter(cache)
    converter.run()