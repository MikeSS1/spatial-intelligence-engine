"""Small, public terrain demonstration on explicitly metric, north-up DEMs.

All products are descriptive derivatives of the supplied raster. This module is
independent of the private Spatial Intelligence Engine implementation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from numpy.lib.stride_tricks import sliding_window_view
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

METHOD = "public-terrain-demo.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_raster(path: Path) -> dict[str, Any]:
    """Report stored metadata without inventing a vertical reference."""
    with rasterio.open(path) as src:
        if src.count != 1:
            raise ValueError("The public demo supports one raster band only.")
        return {
            "path": path.name,
            "sha256": sha256_file(path),
            "width": src.width,
            "height": src.height,
            "crs": src.crs.to_string() if src.crs else None,
            "transform": list(src.transform)[:6],
            "bounds": list(src.bounds),
            "nodata": src.nodata,
            "surface_role": src.tags().get("SURFACE_ROLE", "unknown"),
            "vertical_unit": src.tags().get("VERTICAL_UNIT", "unknown"),
            "vertical_reference": src.tags().get("VERTICAL_REFERENCE", "unknown"),
        }


def load_aoi_mask(path: Path, src: rasterio.io.DatasetReader) -> np.ndarray:
    """Read a WGS84 GeoJSON Polygon and select pixel centers within it."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") if payload.get("type") == "FeatureCollection" else None
    if not isinstance(features, list) or len(features) != 1:
        raise ValueError("AOI must be a GeoJSON FeatureCollection with one Polygon.")
    geometry = features[0].get("geometry", {})
    if geometry.get("type") != "Polygon":
        raise ValueError("AOI must contain one Polygon.")
    projected = transform_geom("EPSG:4326", src.crs, geometry)
    return geometry_mask([projected], (src.height, src.width), src.transform, invert=True)


def load_dem(path: Path, aoi_path: Path | None = None) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Require declared metre XY/Z units; preserve NoData and AOI exclusions."""
    with rasterio.open(path) as src:
        if src.count != 1 or src.crs is None or not src.crs.is_projected:
            raise ValueError("A single-band projected DEM with declared CRS is required.")
        affine = src.transform
        if not (affine.a > 0 and affine.e < 0 and affine.b == 0 and affine.d == 0):
            raise ValueError("This demo supports north-up, unrotated rasters only.")
        if src.crs.linear_units.lower() not in {"metre", "meter"}:
            raise ValueError("Horizontal unit must be metres; no implicit conversion is performed.")
        tags = src.tags()
        if tags.get("VERTICAL_UNIT") != "metre":
            raise ValueError("A declared VERTICAL_UNIT=metre is required; no datum is inferred.")
        if tags.get("SURFACE_ROLE") not in {"DEM", "DTM"}:
            raise ValueError("A declared SURFACE_ROLE=DEM or DTM is required.")
        data = src.read(1, masked=True).astype(np.float64).filled(np.nan)
        valid = np.isfinite(data)
        if aoi_path is not None:
            valid &= load_aoi_mask(aoi_path, src)
        meta = inspect_raster(path)
        meta["resolution_m"] = [float(affine.a), float(-affine.e)]
        meta["aoi_sha256"] = sha256_file(aoi_path) if aoi_path else None
        meta["aoi_policy"] = "pixel center inside WGS84 Polygon; 3x3 valid support required"
        return data, valid, meta


def terrain_metrics(data: np.ndarray, valid: np.ndarray, dx: float, dy: float) -> dict[str, np.ndarray]:
    """Compute deterministic 3x3 terrain descriptors with strict NoData support."""
    if data.ndim != 2 or data.shape != valid.shape or min(data.shape) < 3:
        raise ValueError("DEM and validity mask must share a grid of at least 3x3.")
    if not (np.isfinite(dx) and np.isfinite(dy) and dx > 0 and dy > 0):
        raise ValueError("Cell dimensions must be positive finite metres.")
    valid = valid & np.isfinite(data)
    windows = sliding_window_view(np.pad(data, 1, constant_values=np.nan), (3, 3))
    support = sliding_window_view(np.pad(valid, 1, constant_values=False), (3, 3))
    supported = support.all(axis=(-1, -2))
    center = windows[:, :, 1, 1]
    north, south = windows[:, :, 0, 1], windows[:, :, 2, 1]
    west, east = windows[:, :, 1, 0], windows[:, :, 1, 2]
    dzdx = (east - west) / (2 * dx)
    dzdn = (north - south) / (2 * dy)
    gradient = np.hypot(dzdx, dzdn)
    slope = 100.0 * gradient
    aspect = np.mod(np.degrees(np.arctan2(-dzdx, -dzdn)), 360.0)
    aspect = np.where(gradient > 0, aspect, np.nan)
    azimuth, altitude = np.radians(315.0), np.radians(45.0)
    shade = (np.sin(altitude) - np.cos(altitude) *
             (dzdx * np.sin(azimuth) + dzdn * np.cos(azimuth))) / np.sqrt(1 + gradient**2)
    safe_windows = np.where(support, windows, 0.0)
    neighbor_sum = safe_windows.sum(axis=(-1, -2)) - center
    neighbors = windows.reshape((*data.shape, 9))
    neighbor_deltas = np.delete(neighbors, 4, axis=-1) - center[..., None]
    products = {
        "elevation_m": data,
        "slope_percent": slope,
        "aspect_degrees_clockwise_from_north": aspect,
        "hillshade_0_to_1": np.clip(shade, 0, 1),
        "roughness_range_m": np.max(windows, axis=(-1, -2)) - np.min(windows, axis=(-1, -2)),
        "tpi_m": center - neighbor_sum / 8.0,
        "tri_rms_m": np.sqrt(np.mean(neighbor_deltas**2, axis=-1)),
        "laplacian_curvature_per_m": (east + west - 2 * center) / dx**2 +
                                      (north + south - 2 * center) / dy**2,
    }
    return {name: np.where(valid if name == "elevation_m" else supported, value, np.nan)
            for name, value in products.items()}


def summarize(products: dict[str, np.ndarray], valid: np.ndarray) -> dict[str, Any]:
    values: dict[str, Any] = {"source_valid_cells": int(valid.sum())}
    for name, array in products.items():
        finite = array[np.isfinite(array)]
        values[name] = {"valid_cells": int(finite.size),
                        "min": float(finite.min()) if finite.size else None,
                        "mean": float(finite.mean()) if finite.size else None,
                        "max": float(finite.max()) if finite.size else None}
    return values
