"""Independent analytical checks for the public demonstration formulas."""
import hashlib
import tempfile
import unittest
from pathlib import Path

import rasterio
from rasterio.transform import from_origin
import numpy as np

from src.terrain_demo import inspect_raster, load_dem, terrain_metrics


class TerrainDemoTests(unittest.TestCase):
    def test_shipped_synthetic_sample_and_aoi(self):
        root = Path(__file__).resolve().parents[1]
        raster = root / "sample_data/synthetic_dem.tif"
        aoi = root / "sample_data/example_aoi.geojson"
        info = inspect_raster(raster)
        self.assertEqual(info["crs"], "EPSG:32614")
        self.assertEqual(info["vertical_reference"], "unknown")
        self.assertEqual(info["surface_role"], "DEM")
        data, valid, meta = load_dem(raster, aoi)
        self.assertEqual(int(valid.sum()), 8400)
        self.assertEqual(meta["aoi_sha256"], hashlib.sha256(aoi.read_bytes()).hexdigest())
        self.assertEqual(int(np.isfinite(terrain_metrics(data, valid, 10, 10)["slope_percent"]).sum()), 8000)

    def test_missing_vertical_unit_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown_unit.tif"
            with rasterio.open(path, "w", driver="GTiff", height=3, width=3,
                               count=1, dtype="float32", crs="EPSG:32614",
                               transform=from_origin(500000, 4100000, 10, 10)) as dst:
                dst.write(np.ones((3, 3), dtype="float32"), 1)
                dst.update_tags(SURFACE_ROLE="DEM")
            with self.assertRaisesRegex(ValueError, "VERTICAL_UNIT"):
                load_dem(path)

    def test_plane_slope_aspect_and_zero_curvature(self):
        rows, cols = np.indices((9, 9))
        # East rises 1 m/m; north rises 2 m/m. Downhill azimuth is southwest.
        surface = 100 + cols * 10 - rows * 20
        metrics = terrain_metrics(surface.astype(float), np.ones((9, 9), bool), 10, 10)
        self.assertAlmostEqual(metrics["slope_percent"][4, 4], 100 * np.sqrt(5))
        self.assertAlmostEqual(metrics["aspect_degrees_clockwise_from_north"][4, 4], 206.5650511771)
        self.assertAlmostEqual(metrics["laplacian_curvature_per_m"][4, 4], 0)
        self.assertAlmostEqual(metrics["tpi_m"][4, 4], 0)
        self.assertEqual(np.isfinite(metrics["slope_percent"]).sum(), 49)

    def test_quadratic_bowl_curvature(self):
        rows, cols = np.indices((7, 7))
        bowl = ((cols - 3) * 2) ** 2 + ((rows - 3) * 2) ** 2
        metrics = terrain_metrics(bowl.astype(float), np.ones((7, 7), bool), 2, 2)
        self.assertAlmostEqual(metrics["laplacian_curvature_per_m"][3, 3], 4)
        self.assertAlmostEqual(metrics["roughness_range_m"][3, 3], 8)
        self.assertAlmostEqual(metrics["tpi_m"][3, 3], -6)
        self.assertAlmostEqual(metrics["tri_rms_m"][3, 3], np.sqrt(40))
        self.assertTrue(np.isnan(metrics["aspect_degrees_clockwise_from_north"][3, 3]))

    def test_nodata_and_boundary_are_excluded(self):
        surface = np.ones((5, 5), float)
        surface[2, 2] = np.nan
        valid = np.isfinite(surface)
        metrics = terrain_metrics(surface, valid, 1, 1)
        self.assertEqual(np.isfinite(metrics["slope_percent"]).sum(), 0)
        self.assertEqual(np.isfinite(metrics["elevation_m"]).sum(), 24)

    def test_invalid_cell_dimensions_refused(self):
        with self.assertRaises(ValueError):
            terrain_metrics(np.ones((3, 3)), np.ones((3, 3), bool), 0, 1)


if __name__ == "__main__":
    unittest.main()
