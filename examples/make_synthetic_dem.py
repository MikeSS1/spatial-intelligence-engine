"""Create a small, wholly synthetic GeoTIFF and AOI for public examples."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows, cols, cell = 128, 128, 10.0
    x = (np.arange(cols) + 0.5) * cell
    y = (np.arange(rows) + 0.5) * cell
    east, south = np.meshgrid(x, y)
    terrain = (180 + 0.012 * east - 0.008 * south +
               4 * np.exp(-((east - 700)**2 + (south - 630)**2) / 45000) +
               0.7 * np.sin(east / 75) * np.cos(south / 90))
    terrain = terrain.astype("float32")
    terrain[24:32, 83:91] = -9999  # an intentional NoData patch
    raster_path = OUT / "synthetic_dem.tif"
    with rasterio.open(raster_path, "w", driver="GTiff", height=rows, width=cols,
                       count=1, dtype="float32", crs="EPSG:32614",
                       transform=from_origin(500000, 4100000, cell, cell),
                       nodata=-9999, compress="deflate") as dst:
        dst.write(terrain, 1)
        dst.update_tags(SURFACE_ROLE="DEM", VERTICAL_UNIT="metre",
                        VERTICAL_REFERENCE="unknown", SOURCE="synthetic formula in examples/make_synthetic_dem.py")
    to_wgs84 = Transformer.from_crs("EPSG:32614", "EPSG:4326", always_xy=True)
    corners_xy = [(500180, 4099820), (501100, 4099820),
                  (501100, 4098900), (500180, 4098900), (500180, 4099820)]
    corners = [list(to_wgs84.transform(*xy)) for xy in corners_xy]
    aoi = {"type": "FeatureCollection", "features": [{"type": "Feature",
           "properties": {"name": "Synthetic demonstration AOI"},
           "geometry": {"type": "Polygon", "coordinates": [corners]}}]}
    (OUT / "example_aoi.geojson").write_text(json.dumps(aoi, indent=2) + "\n", encoding="utf-8")
    print(raster_path)


if __name__ == "__main__":
    main()
