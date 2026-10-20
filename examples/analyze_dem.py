"""Inspect or analyze a DEM using the independent public terrain demo."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.terrain_demo import METHOD, inspect_raster, load_dem, summarize, terrain_metrics  # noqa: E402


def render(products: dict[str, np.ndarray], output: Path) -> None:
    panels = [
        ("elevation_m", "Elevation (m)", "terrain"),
        ("slope_percent", "Slope (%)", "magma"),
        ("aspect_degrees_clockwise_from_north", "Downhill aspect (°)", "twilight"),
        ("hillshade_0_to_1", "Hillshade (0–1)", "gray"),
        ("roughness_range_m", "3×3 range (m)", "viridis"),
        ("tpi_m", "TPI (m)", "coolwarm"),
        ("tri_rms_m", "TRI RMS (m)", "viridis"),
        ("laplacian_curvature_per_m", "Laplacian (1/m)", "coolwarm"),
    ]
    fig, axes = plt.subplots(2, 4, figsize=(14, 7), constrained_layout=True)
    for ax, (key, title, cmap) in zip(axes.flat, panels):
        field = np.ma.masked_invalid(products[key])
        image = ax.imshow(field, cmap=cmap, origin="upper", interpolation="nearest")
        if key == "elevation_m":
            levels = np.linspace(float(field.min()), float(field.max()), 9)
            ax.contour(field, levels=levels, colors="black", linewidths=0.35, alpha=0.6)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Column")
        ax.set_ylabel("Row")
        fig.colorbar(image, ax=ax, shrink=0.75)
    fig.suptitle("Synthetic DEM terrain descriptors — public demonstration", fontsize=13)
    fig.savefig(output, dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raster", type=Path)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--aoi", type=Path, help="Single WGS84 GeoJSON Polygon; pixel-center selection")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "demo_output")
    args = parser.parse_args()
    if args.inspect_only:
        print(json.dumps(inspect_raster(args.raster), indent=2))
        return
    data, valid, metadata = load_dem(args.raster, args.aoi)
    dx, dy = metadata["resolution_m"]
    products = terrain_metrics(data, valid, dx, dy)
    result = {"method": METHOD, "source": metadata, "summary": summarize(products, valid),
              "limitations": ["Synthetic data, no field accuracy claim.",
                              "Vertical reference is source-declared and not independently validated; relative descriptors only.",
                              "Strict 3x3 support excludes edges and cells touching NoData or AOI boundary.",
                              "Aspect is undefined on flat cells; curvature is a discrete Laplacian."]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    render(products, args.output_dir / "terrain_overview.png")
    print(json.dumps({"source_valid_cells": result["summary"]["source_valid_cells"],
                      "slope_supported_cells": result["summary"]["slope_percent"]["valid_cells"],
                      "output_dir": str(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()
