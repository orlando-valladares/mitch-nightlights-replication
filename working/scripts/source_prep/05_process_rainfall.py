from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from rasterio.warp import transform_bounds

from pipeline_config import DATA_DIR, PROCESSED_DIR, RAW_DIR, WEB_DIR, ensure_project_dirs, output_path, resolve_path
from pipeline_utils import ensure_muni_fields


def discover_rainfall(explicit: Path | None) -> Path | None:
    if explicit is not None:
        explicit = resolve_path(explicit)
        if explicit and explicit.exists():
            return explicit
        raise FileNotFoundError(f"Rainfall GeoTIFF not found: {explicit}")
    patterns = ["*chirps*.tif", "*CHIRPS*.tif", "*rain*.tif", "*rainfall*.tif"]
    for root in [DATA_DIR, RAW_DIR]:
        for pattern in patterns:
            matches = sorted(root.rglob(pattern)) if root.exists() else []
            if matches:
                return matches[0]
    return None


def load_boundaries(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing analytical boundaries: {path}. Run scripts/03_build_distance_exposure.py first.")
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    gdf["geometry"] = gdf.geometry.make_valid()
    return ensure_muni_fields(gdf).loc[lambda x: x.geometry.notna() & ~x.geometry.is_empty].reset_index(drop=True)


def cumulative_rainfall_array(arr: np.ndarray | np.ma.MaskedArray, nodata: float | None) -> np.ndarray | np.ma.MaskedArray:
    """Return cumulative rainfall per pixel, summing bands when a daily stack is supplied."""
    if arr.ndim == 3:
        if np.ma.isMaskedArray(arr):
            data = np.ma.sum(arr, axis=0)
        else:
            data = np.sum(arr, axis=0)
    else:
        data = arr
    if nodata is not None and not np.ma.isMaskedArray(data):
        data = np.where(data == nodata, np.nan, data)
    return data


def zonal_rainfall(boundaries: gpd.GeoDataFrame, rainfall_path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    with rasterio.open(rainfall_path) as src:
        b_raster = boundaries.to_crs(src.crs)
        nodata = src.nodata
        for idx, muni in b_raster.iterrows():
            try:
                arr, _ = mask(src, [muni.geometry], crop=True, filled=False, indexes=1)
            except ValueError:
                values = np.array([], dtype=float)
            else:
                data = cumulative_rainfall_array(arr, nodata)
                if np.ma.isMaskedArray(data):
                    values = data.compressed().astype(float)
                else:
                    values = np.asarray(data, dtype=float).ravel()
                if nodata is not None:
                    values = values[values != nodata]
                values = values[np.isfinite(values)]
            rows.append(
                {
                    "muni_key": boundaries.loc[idx, "muni_key"],
                    "country_name": boundaries.loc[idx, "country_name"] if "country_name" in boundaries.columns else "",
                    "department_name": boundaries.loc[idx, "department_name"] if "department_name" in boundaries.columns else "",
                    "municipality_name": boundaries.loc[idx, "municipality_name"] if "municipality_name" in boundaries.columns else "",
                    "mean_rainfall_mm": float(np.mean(values)) if len(values) else np.nan,
                    "max_rainfall_mm": float(np.max(values)) if len(values) else np.nan,
                    "p90_rainfall_mm": float(np.percentile(values, 90)) if len(values) else np.nan,
                    "rainfall_pixel_count": int(len(values)),
                    "area_weighted_rainfall_mm": float(np.mean(values)) if len(values) else np.nan,
                    "rainfall_weighting_note": "simple raster-cell mean; exact pixel-area weighting not applied",
                }
            )
    return pd.DataFrame(rows)


def write_png_overlay(boundaries: gpd.GeoDataFrame, rainfall_path: Path) -> None:
    try:
        os.environ.setdefault("MPLCONFIGDIR", str(output_path(WEB_DIR / ".matplotlib")))
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        output_path(WEB_DIR / "chirps_overlay_skipped.txt").write_text(
            "matplotlib is not installed; rainfall PNG overlay was not created.\n",
            encoding="utf-8",
        )
        return

    with rasterio.open(rainfall_path) as src:
        geom = boundaries.to_crs(src.crs).unary_union
        arr, transform = mask(src, [geom], crop=True, filled=False)
        data = cumulative_rainfall_array(arr, src.nodata)
        data = np.asarray(data.filled(np.nan) if np.ma.isMaskedArray(data) else data, dtype=float)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        if not np.isfinite(data).any():
            return
        png_path = output_path(WEB_DIR / "chirps_mitch_rainfall_overlay.png")
        fig, ax = plt.subplots(figsize=(8, 8), dpi=180)
        ax.axis("off")
        im = ax.imshow(data, cmap="Blues", alpha=np.where(np.isfinite(data), 0.68, 0.0))
        im.set_clim(np.nanpercentile(data, 5), np.nanpercentile(data, 98))
        fig.subplots_adjust(0, 0, 1, 1)
        fig.savefig(png_path, transparent=True, pad_inches=0)
        plt.close(fig)

        height, width = data.shape
        west, north = transform * (0, 0)
        east, south = transform * (width, height)
        bounds = transform_bounds(src.crs, "EPSG:4326", west, south, east, north, densify_pts=21)
        meta = {
            "png": str(png_path),
            "bounds_wgs84": {
                "west": bounds[0],
                "south": bounds[1],
                "east": bounds[2],
                "north": bounds[3],
            },
            "source": str(rainfall_path),
        }
        output_path(WEB_DIR / "chirps_mitch_rainfall_overlay.json").write_text(
            json.dumps(meta, indent=2) + "\n",
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calculate municipality-level CHIRPS rainfall exposure.")
    parser.add_argument("--rainfall", type=Path, default=None, help="CHIRPS Mitch-duration cumulative rainfall GeoTIFF.")
    parser.add_argument("--boundaries", type=Path, default=PROCESSED_DIR / "municipalities_adm2_analytical.geojson")
    args = parser.parse_args(argv)

    ensure_project_dirs()
    rainfall_path = discover_rainfall(args.rainfall)
    if rainfall_path is None:
        output_path(PROCESSED_DIR / "rainfall_missing.txt").write_text(
            "No CHIRPS rainfall GeoTIFF was found. Pass --rainfall path/to/file.tif.\n",
            encoding="utf-8",
        )
        print("No CHIRPS rainfall GeoTIFF found; wrote rainfall_missing.txt.")
        return 0
    boundaries = load_boundaries(args.boundaries)
    stats = zonal_rainfall(boundaries, rainfall_path)
    stats.to_csv(output_path(PROCESSED_DIR / "municipality_mitch_rainfall_exposure.csv"), index=False)
    write_png_overlay(boundaries, rainfall_path)
    print(f"Wrote rainfall exposure for {len(stats)} municipalities from {rainfall_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
