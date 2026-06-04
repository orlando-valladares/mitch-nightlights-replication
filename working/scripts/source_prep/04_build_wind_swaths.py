from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union

try:
    import rasterio
    from affine import Affine
    from rasterio.features import shapes
except ModuleNotFoundError:
    rasterio = None
    Affine = None
    shapes = None

from pipeline_config import DEFAULT_EBTRK_TXT, PROCESSED_DIR, ensure_project_dirs, output_path
from pipeline_utils import ensure_muni_fields, to_numeric


GEOD = Geod(ellps="WGS84")
AREA_CRS = "EPSG:6933"


EBTRK_COLUMNS = [
    "storm_id",
    "storm_name",
    "mmddhh",
    "year",
    "lat",
    "lon_w",
    "vmax_kt",
    "pressure_mb",
    "rmw_nm",
    "eye_diameter_nm",
    "poci_mb",
    "roci_nm",
    "r34_ne_nm",
    "r34_se_nm",
    "r34_sw_nm",
    "r34_nw_nm",
    "r50_ne_nm",
    "r50_se_nm",
    "r50_sw_nm",
    "r50_nw_nm",
    "r64_ne_nm",
    "r64_se_nm",
    "r64_sw_nm",
    "r64_nw_nm",
    "storm_type",
    "distance_to_land_km",
    "structure_source_code",
]


def parse_ebtrk(path: Path) -> pd.DataFrame:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or line.lower().startswith("description"):
                continue
            if not line.upper().startswith("AL"):
                continue
            first_fields = line.split(maxsplit=12)
            if len(first_fields) < 13:
                continue
            try:
                radii_text, storm_type, distance_to_land, source_code = first_fields[12].rsplit(maxsplit=3)
            except ValueError:
                continue
            radii_text = radii_text.ljust(38)
            radii = []
            for group in [radii_text[0:12], radii_text[13:25], radii_text[26:38]]:
                radii.extend(group[i : i + 3].strip() for i in range(0, 12, 3))
            parts = [*first_fields[:12], *radii, storm_type, distance_to_land, source_code]
            rows.append(parts)
    if not rows:
        raise RuntimeError(f"No EBTRK data rows were parsed from {path}")
    df = pd.DataFrame(rows, columns=EBTRK_COLUMNS)
    numeric_cols = [col for col in EBTRK_COLUMNS if col not in {"storm_id", "storm_name", "mmddhh", "storm_type", "structure_source_code"}]
    for col in numeric_cols:
        df[col] = to_numeric(df[col])
    df["storm_name"] = df["storm_name"].astype(str).str.upper()
    df["lon"] = -df["lon_w"].abs()
    df["iso_time"] = pd.to_datetime(
        df["year"].astype("Int64").astype(str)
        + "-"
        + df["mmddhh"].astype(str).str.zfill(6).str.slice(0, 2)
        + "-"
        + df["mmddhh"].astype(str).str.zfill(6).str.slice(2, 4)
        + "T"
        + df["mmddhh"].astype(str).str.zfill(6).str.slice(4, 6)
        + ":00:00Z",
        errors="coerce",
        utc=True,
    )
    return df


def mitch_ebtrk(path: Path) -> pd.DataFrame:
    df = parse_ebtrk(path)
    mask = df["year"].eq(1998) & df["storm_name"].eq("MITCH")
    out = df.loc[mask].dropna(subset=["iso_time", "lat", "lon"]).sort_values("iso_time").reset_index(drop=True)
    if out.empty:
        raise RuntimeError("No Hurricane Mitch 1998 rows found in Extended Best Track.")
    return out


def sector_polygon(lon: float, lat: float, radius_km: float, start_bearing: float, end_bearing: float) -> Polygon | None:
    if not np.isfinite(radius_km) or radius_km <= 0:
        return None
    bearings = np.linspace(start_bearing, end_bearing, max(4, int((end_bearing - start_bearing) / 5) + 1))
    arc = []
    for bearing in bearings:
        x, y, _ = GEOD.fwd(lon, lat, bearing, radius_km * 1000.0)
        arc.append((x, y))
    coords = [(lon, lat), *arc, (lon, lat)]
    return Polygon(coords)


def timestamp_swath(row: pd.Series, threshold: str) -> Polygon | None:
    quadrants = [
        ("ne", 0.0, 90.0),
        ("se", 90.0, 180.0),
        ("sw", 180.0, 270.0),
        ("nw", 270.0, 360.0),
    ]
    pieces = []
    for quad, start, end in quadrants:
        radius_nm = row.get(f"{threshold}_{quad}_nm")
        radius_km = float(radius_nm) * 1.852 if pd.notna(radius_nm) else np.nan
        piece = sector_polygon(float(row["lon"]), float(row["lat"]), radius_km, start, end)
        if piece is not None and piece.is_valid and not piece.is_empty:
            pieces.append(piece)
    if not pieces:
        return None
    return unary_union(pieces)


def build_swaths(ebtrk: pd.DataFrame) -> dict[str, gpd.GeoDataFrame]:
    swaths: dict[str, gpd.GeoDataFrame] = {}
    for threshold in ["r34", "r50", "r64"]:
        pieces = [timestamp_swath(row, threshold) for _, row in ebtrk.iterrows()]
        pieces = [geom for geom in pieces if geom is not None and not geom.is_empty]
        if pieces:
            unioned = unary_union(pieces)
            gdf = gpd.GeoDataFrame(
                [{"storm": "MITCH", "season": 1998, "threshold": threshold.upper()}],
                geometry=[unioned],
                crs="EPSG:4326",
            )
        else:
            gdf = gpd.GeoDataFrame(columns=["storm", "season", "threshold", "geometry"], geometry="geometry", crs="EPSG:4326")
        swaths[threshold] = gdf
    return swaths


def load_boundaries(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing analytical boundaries: {path}. Run scripts/03_build_distance_exposure.py first.")
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = ensure_muni_fields(gdf)
    return gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)


def intersect_swaths(boundaries: gpd.GeoDataFrame, swaths: dict[str, gpd.GeoDataFrame]) -> pd.DataFrame:
    b_area = boundaries.to_crs(AREA_CRS)
    areas = b_area.geometry.area.replace(0, np.nan)
    out = pd.DataFrame(
        {
            "muni_key": boundaries["muni_key"],
            "country_name": boundaries.get("country_name", pd.Series("", index=boundaries.index)),
            "department_name": boundaries.get("department_name", pd.Series("", index=boundaries.index)),
            "municipality_name": boundaries.get("municipality_name", pd.Series("", index=boundaries.index)),
        }
    )
    for threshold in ["r34", "r50", "r64"]:
        gdf = swaths[threshold]
        if gdf.empty:
            shares = pd.Series(0.0, index=boundaries.index)
        else:
            swath_geom = gdf.to_crs(AREA_CRS).geometry.iloc[0]
            shares = b_area.geometry.intersection(swath_geom).area / areas
            shares = shares.fillna(0.0).clip(0, 1)
        out[f"share_area_{threshold}"] = shares.round(6)
        out[f"any_{threshold}"] = shares.gt(0).astype(int)
    out["max_swath_category"] = "none"
    out.loc[out["any_r34"].eq(1), "max_swath_category"] = "r34"
    out.loc[out["any_r50"].eq(1), "max_swath_category"] = "r50"
    out.loc[out["any_r64"].eq(1), "max_swath_category"] = "r64"
    return out


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
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def quadrant_from_bearing(bearing: float) -> str:
    bearing = bearing % 360.0
    if bearing < 90:
        return "ne"
    if bearing < 180:
        return "se"
    if bearing < 270:
        return "sw"
    return "nw"


def interpolate_wind(distance_km: float, vmax: float, rmw_km: float, r64: float, r50: float, r34: float) -> float:
    if not np.isfinite(distance_km) or not np.isfinite(vmax) or not np.isfinite(r34) or r34 <= 0:
        return np.nan
    if not np.isfinite(rmw_km) or rmw_km <= 0:
        return np.nan
    anchors = [(rmw_km, vmax)]
    if np.isfinite(r64) and r64 > rmw_km:
        anchors.append((r64, 64.0))
    if np.isfinite(r50) and r50 > anchors[-1][0]:
        anchors.append((r50, 50.0))
    if np.isfinite(r34) and r34 > anchors[-1][0]:
        anchors.append((r34, 34.0))
    if distance_km <= anchors[0][0]:
        return float(vmax)
    for (d0, v0), (d1, v1) in zip(anchors[:-1], anchors[1:]):
        if d0 <= distance_km <= d1:
            frac = (distance_km - d0) / (d1 - d0)
            return float(v0 + frac * (v1 - v0))
    return np.nan


def continuous_wind_grid(boundaries: gpd.GeoDataFrame, ebtrk: pd.DataFrame, grid_km: float) -> tuple[np.ndarray, Affine, CRS]:
    valid_rmw = ebtrk["rmw_nm"].dropna().gt(0).any()
    if not valid_rmw:
        raise RuntimeError("RMW is missing for Mitch in EBTRK; skipping continuous wind grid.")
    metric_crs = metric_crs_for(boundaries)
    b_metric = boundaries.to_crs(metric_crs)
    minx, miny, maxx, maxy = b_metric.total_bounds
    pad = 100_000
    minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
    cell = grid_km * 1000.0
    width = int(np.ceil((maxx - minx) / cell))
    height = int(np.ceil((maxy - miny) / cell))
    transform = Affine.translation(minx, maxy) * Affine.scale(cell, -cell)
    xs = minx + (np.arange(width) + 0.5) * cell
    ys = maxy - (np.arange(height) + 0.5) * cell
    xx, yy = np.meshgrid(xs, ys)
    to_wgs84 = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)
    lon_grid, lat_grid = to_wgs84.transform(xx, yy)
    max_wind = np.full((height, width), np.nan, dtype="float32")

    for _, row in ebtrk.iterrows():
        if pd.isna(row["rmw_nm"]) or row["rmw_nm"] <= 0:
            continue
        center_x, center_y = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True).transform(row["lon"], row["lat"])
        dist_km = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2) / 1000.0
        flat_lon = lon_grid.ravel()
        flat_lat = lat_grid.ravel()
        bearings = np.array(
            [GEOD.inv(float(row["lon"]), float(row["lat"]), float(lon), float(lat))[0] for lon, lat in zip(flat_lon, flat_lat)]
        )
        bearings = (bearings.reshape((height, width)) + 360.0) % 360.0
        estimate = np.full((height, width), np.nan, dtype="float32")
        for quad in ["ne", "se", "sw", "nw"]:
            if quad == "ne":
                mask = (bearings >= 0) & (bearings < 90)
            elif quad == "se":
                mask = (bearings >= 90) & (bearings < 180)
            elif quad == "sw":
                mask = (bearings >= 180) & (bearings < 270)
            else:
                mask = bearings >= 270
            r64 = row.get(f"r64_{quad}_nm", np.nan) * 1.852
            r50 = row.get(f"r50_{quad}_nm", np.nan) * 1.852
            r34 = row.get(f"r34_{quad}_nm", np.nan) * 1.852
            rmw = row["rmw_nm"] * 1.852
            vectorized = np.vectorize(interpolate_wind, otypes=[float])
            estimate[mask] = vectorized(dist_km[mask], row["vmax_kt"], rmw, r64, r50, r34)
        max_wind = np.fmax(max_wind, estimate)

    return max_wind, transform, metric_crs


def write_continuous_outputs(boundaries: gpd.GeoDataFrame, ebtrk: pd.DataFrame, grid_km: float) -> None:
    if rasterio is None or shapes is None:
        raise RuntimeError("rasterio is not installed; skipping continuous wind grid.")
    data, transform, crs = continuous_wind_grid(boundaries, ebtrk, grid_km)
    tif_path = output_path(PROCESSED_DIR / "mitch_max_wind_kt.tif")
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)

    contour_features = []
    for threshold in [34, 50, 64]:
        mask = np.nan_to_num(data, nan=0.0) >= threshold
        if not mask.any():
            continue
        geoms = [shape(geom) for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=transform) if value == 1]
        unioned = unary_union(geoms)
        contour_features.append({"threshold_kt": threshold, "geometry": unioned})
    if contour_features:
        contours = gpd.GeoDataFrame(contour_features, geometry="geometry", crs=crs).to_crs("EPSG:4326")
        contours.to_file(output_path(PROCESSED_DIR / "mitch_max_wind_contours.geojson"), driver="GeoJSON")

    points = []
    height, width = data.shape
    for row in range(height):
        for col in range(width):
            val = data[row, col]
            if np.isfinite(val):
                x, y = transform * (col + 0.5, row + 0.5)
                points.append({"max_estimated_wind_kt": float(val), "geometry": Point(x, y)})
    grid = gpd.GeoDataFrame(points, geometry="geometry", crs=crs)
    b_metric = boundaries.to_crs(crs)
    rows = []
    for _, muni in b_metric.iterrows():
        vals = grid.loc[grid.within(muni.geometry), "max_estimated_wind_kt"]
        rows.append(
            {
                "muni_key": muni["muni_key"],
                "max_estimated_wind_kt": float(vals.max()) if len(vals) else np.nan,
                "mean_estimated_wind_kt": float(vals.mean()) if len(vals) else np.nan,
            }
        )
    pd.DataFrame(rows).to_csv(output_path(PROCESSED_DIR / "municipality_mitch_max_wind.csv"), index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Mitch wind-radii swaths and municipality exposure.")
    parser.add_argument("--ebtrk", type=Path, default=DEFAULT_EBTRK_TXT)
    parser.add_argument("--boundaries", type=Path, default=PROCESSED_DIR / "municipalities_adm2_analytical.geojson")
    parser.add_argument("--make-continuous", action="store_true", help="Also build an optional continuous wind grid.")
    parser.add_argument("--grid-km", type=float, default=5.0, help="Continuous wind grid resolution in kilometers.")
    args = parser.parse_args(argv)

    ensure_project_dirs()
    if not args.ebtrk.exists():
        raise FileNotFoundError(f"Missing Extended Best Track file: {args.ebtrk}. Run scripts/01_download_data.py first.")
    boundaries = load_boundaries(args.boundaries)
    ebtrk = mitch_ebtrk(args.ebtrk)
    ebtrk.to_csv(output_path(PROCESSED_DIR / "mitch_ebtrk_wind_radii.csv"), index=False)

    swaths = build_swaths(ebtrk)
    for threshold, gdf in swaths.items():
        gdf.to_file(output_path(PROCESSED_DIR / f"mitch_swath_{threshold}.geojson"), driver="GeoJSON")
    exposure = intersect_swaths(boundaries, swaths)
    exposure.to_csv(output_path(PROCESSED_DIR / "municipality_mitch_wind_swath_exposure.csv"), index=False)

    if args.make_continuous:
        try:
            write_continuous_outputs(boundaries, ebtrk, args.grid_km)
        except RuntimeError as exc:
            output_path(PROCESSED_DIR / "mitch_continuous_wind_skipped.txt").write_text(str(exc) + "\n", encoding="utf-8")

    print(f"Wrote wind swath exposure for {len(exposure)} municipalities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
