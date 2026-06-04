from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import LineString

from pipeline_config import EXTERNAL_DIR, PROCESSED_DIR, ensure_project_dirs, output_path, resolve_path
from pipeline_utils import ensure_muni_fields, to_numeric


def discover_boundary_files(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        explicit = resolve_path(explicit)
        if explicit is None or not explicit.exists():
            raise FileNotFoundError(f"Boundary file not found: {explicit}")
        return [explicit]
    processed = PROCESSED_DIR / "municipalities_adm2_analytical.geojson"
    if processed.exists():
        return [processed]
    geoboundaries = sorted(EXTERNAL_DIR.glob("geoboundaries_adm2_*.geojson"))
    if geoboundaries:
        return geoboundaries
    raise FileNotFoundError(
        "No boundary file found. Pass --boundaries or run scripts/01_download_data.py "
        "to download GeoBoundaries ADM2 fallback files."
    )


def load_boundaries(boundary_files: list[Path], scope: str) -> gpd.GeoDataFrame:
    frames = [gpd.read_file(path) for path in boundary_files]
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=frames[0].crs)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = ensure_muni_fields(gdf)
    if "muni_key" not in gdf.columns:
        gdf["muni_key"] = [f"muni_{i:05d}" for i in range(len(gdf))]
    if scope.lower() == "honduras":
        country = gdf.get("country_name", pd.Series("", index=gdf.index)).astype(str).str.lower()
        iso = gdf.get("shapeISO", pd.Series("", index=gdf.index)).astype(str).str.upper()
        gdf = gdf.loc[country.eq("honduras") | iso.eq("HND")].copy()
    return gdf.reset_index(drop=True)


def metric_crs_for(gdf: gpd.GeoDataFrame) -> CRS:
    try:
        crs = gdf.estimate_utm_crs()
        if crs is not None:
            return CRS.from_user_input(crs)
    except Exception:
        pass
    minx, miny, maxx, maxy = gdf.total_bounds
    lon = (minx + maxx) / 2
    lat = (miny + maxy) / 2
    zone = int((lon + 180) // 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)


def load_track(track_csv: Path) -> gpd.GeoDataFrame:
    track = pd.read_csv(track_csv)
    track["iso_time"] = pd.to_datetime(track["iso_time"], utc=True, errors="coerce")
    track["lat"] = to_numeric(track["lat"])
    track["lon"] = to_numeric(track["lon"])
    track["wind_kt"] = to_numeric(track["wind_kt"])
    track["pressure_mb"] = to_numeric(track["pressure_mb"])
    track = track.dropna(subset=["iso_time", "lat", "lon"]).sort_values("iso_time").reset_index(drop=True)
    return gpd.GeoDataFrame(track, geometry=gpd.points_from_xy(track["lon"], track["lat"]), crs="EPSG:4326")


def compute_distance_exposure(boundaries: gpd.GeoDataFrame, track: gpd.GeoDataFrame) -> pd.DataFrame:
    crs = metric_crs_for(boundaries)
    b_metric = boundaries.to_crs(crs)
    t_metric = track.to_crs(crs)
    line = LineString([pt for pt in t_metric.geometry])
    points = list(t_metric.geometry)
    winds = pd.to_numeric(track["wind_kt"], errors="coerce").to_numpy()
    pressures = pd.to_numeric(track["pressure_mb"], errors="coerce").to_numpy()
    times = pd.to_datetime(track["iso_time"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy()

    rows: list[dict[str, object]] = []
    for idx, geom in enumerate(b_metric.geometry):
        centroid = geom.centroid
        point_dist_km = np.array([centroid.distance(pt) / 1000.0 for pt in points], dtype=float)
        nearest_idx = int(np.nanargmin(point_dist_km))
        row = {
            "muni_key": boundaries.loc[idx, "muni_key"],
            "country_name": boundaries.loc[idx, "country_name"] if "country_name" in boundaries.columns else "",
            "department_name": boundaries.loc[idx, "department_name"] if "department_name" in boundaries.columns else "",
            "municipality_name": boundaries.loc[idx, "municipality_name"] if "municipality_name" in boundaries.columns else "",
            "min_distance_to_track_km": geom.distance(line) / 1000.0,
            "centroid_min_distance_to_track_km": float(np.nanmin(point_dist_km)),
            "nearest_track_time": times[nearest_idx],
            "nearest_track_wind_kt": winds[nearest_idx],
            "nearest_track_pressure_mb": pressures[nearest_idx],
        }
        for km in [50, 100, 150, 200]:
            mask = point_dist_km <= km
            row[f"max_track_wind_within_{km}km"] = float(np.nanmax(winds[mask])) if mask.any() else np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    for col in ["min_distance_to_track_km", "centroid_min_distance_to_track_km"]:
        out[col] = out[col].round(3)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build municipality distance exposure to Hurricane Mitch.")
    parser.add_argument("--boundaries", type=Path, default=None, help="ADM2 boundary file, shapefile, or GeoJSON.")
    parser.add_argument(
        "--scope",
        choices=["central-america", "honduras"],
        default="central-america",
        help="Keep all loaded Central America boundaries or only Honduras.",
    )
    parser.add_argument("--track-csv", type=Path, default=PROCESSED_DIR / "mitch_ibtracs_track.csv")
    args = parser.parse_args(argv)

    ensure_project_dirs()
    if not args.track_csv.exists():
        raise FileNotFoundError(f"Missing track CSV: {args.track_csv}. Run scripts/02_process_track.py first.")

    boundaries = load_boundaries(discover_boundary_files(args.boundaries), scope=args.scope)
    if boundaries.empty:
        raise RuntimeError("No municipality polygons were loaded after scope filtering.")
    boundaries.to_file(output_path(PROCESSED_DIR / "municipalities_adm2_analytical.geojson"), driver="GeoJSON")

    track = load_track(args.track_csv)
    exposure = compute_distance_exposure(boundaries, track)
    exposure.to_csv(output_path(PROCESSED_DIR / "municipality_mitch_distance_exposure.csv"), index=False)
    print(f"Wrote distance exposure for {len(exposure)} municipalities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
