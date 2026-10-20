# Public demonstration architecture

```text
Synthetic GeoTIFF + optional WGS84 polygon
          │
          ▼
Raster metadata / SHA-256 inspection
          │
          ▼
Explicit metre CRS and vertical-unit checks
          │
          ▼
NoData + AOI validity mask → strict 3×3 support
          │
          ▼
Deterministic terrain arrays → structured summary JSON + overview PNG
```

`src/terrain_demo.py` contains the public calculation and validation boundary. `examples/analyze_dem.py` is a thin command-line presentation layer; it does not recalculate statistics. `examples/make_synthetic_dem.py` creates every spatial input in `sample_data/`. `tests/` independently checks planar slope/aspect, a quadratic surface, NoData, and refusal behavior.

The public module is purpose-built from standard raster and array operations. It is not a copy of private production code. The synthetic sample has no surveyed or independently validated vertical reference. Descriptors are exploratory and require professional review before real engineering use.
