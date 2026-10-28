from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from pipeline_config import DEFAULT_IBTRACS_CSV, NHC_MITCH_TCR_URL, PROCESSED_DIR, ensure_project_dirs, output_path
from pipeline_utils import clean_column_names, to_numeric


def read_ibtracs(path: Path) -> pd.DataFrame:
    df = clean_column_names(pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False))
    season = pd.to_numeric(df.get("SEASON"), errors="coerce")
    df = df.loc[season.notna()].copy()
    df["SEASON"] = season.loc[df.index].astype(int)
    return df


def first_numeric(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    out = pd.Series(pd.NA, index=df.index, dtype="Float64")
    for col in columns:
        if col in df.columns:
            vals = to_numeric(df[col]).astype("Float64")
            out = out.fillna(vals)
    return out


def process_mitch_track(ibtracs_path: Path) -> pd.DataFrame:
    df = read_ibtracs(ibtracs_path)
    for col in ["NAME", "BASIN", "TRACK_TYPE"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    mask = (
        df["SEASON"].eq(1998)
        & df["NAME"].str.upper().eq("MITCH")
        & df["BASIN"].str.upper().eq("NA")
        & df["TRACK_TYPE"].str.upper().eq("MAIN")
    )
    mitch = df.loc[mask].copy()
    if mitch.empty:
        raise RuntimeError("No Mitch 1998 main-track rows found in IBTrACS.")

    mitch["iso_time"] = pd.to_datetime(mitch["ISO_TIME"], errors="coerce", utc=True)
    mitch["lat"] = to_numeric(mitch["LAT"])
    mitch["lon"] = to_numeric(mitch["LON"])
    mitch["wind_kt"] = first_numeric(mitch, ["USA_WIND", "WMO_WIND"])
    mitch["pressure_mb"] = first_numeric(mitch, ["USA_PRES", "WMO_PRES"])
    status_cols = [c for c in ["USA_STATUS", "NATURE"] if c in mitch.columns]
    mitch["status"] = mitch[status_cols[0]].astype(str).str.strip() if status_cols else ""

    keep = [
        "SID",
        "SEASON",
        "NUMBER",
        "BASIN",
        "NAME",
        "TRACK_TYPE",
        "iso_time",
        "lat",
        "lon",
        "wind_kt",
        "pressure_mb",
        "status",
    ]
    for col in ["NATURE", "USA_WIND", "WMO_WIND", "USA_PRES", "WMO_PRES", "USA_SSHS", "DIST2LAND", "LANDFALL"]:
        if col in mitch.columns and col not in keep:
            keep.append(col)
    out = mitch[keep].dropna(subset=["iso_time", "lat", "lon"]).sort_values("iso_time").reset_index(drop=True)
    out["iso_time"] = out["iso_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def save_geojson(track: pd.DataFrame) -> None:
    gdf = gpd.GeoDataFrame(
        track,
        geometry=gpd.points_from_xy(track["lon"], track["lat"]),
        crs="EPSG:4326",
    )
    gdf.to_file(output_path(PROCESSED_DIR / "mitch_track_points.geojson"), driver="GeoJSON")

    line = LineString(list(zip(track["lon"], track["lat"])))
    line_gdf = gpd.GeoDataFrame(
        [{"storm": "MITCH", "season": 1998, "source": "NOAA IBTrACS v04r01"}],
        geometry=[line],
        crs="EPSG:4326",
    )
    line_gdf.to_file(output_path(PROCESSED_DIR / "mitch_track_line.geojson"), driver="GeoJSON")


def validation_table(track: pd.DataFrame) -> pd.DataFrame:
    times = pd.to_datetime(track["iso_time"], utc=True)
    peak_idx = pd.to_numeric(track["wind_kt"], errors="coerce").idxmax()
    landfall_target = pd.Timestamp("1998-10-29T12:00:00Z")
    landfall_idx = (times - landfall_target).abs().idxmin()
    peak = track.loc[peak_idx]
    landfall = track.loc[landfall_idx]
    return pd.DataFrame(
        [
            {
                "check": "Peak intensity",
                "nhc_report_reference": NHC_MITCH_TCR_URL,
                "nhc_value": "155 kt on 1998-10-26 1800 UTC; central pressure 905 mb",
                "ibtracs_time": peak["iso_time"],
                "ibtracs_wind_kt": peak["wind_kt"],
                "ibtracs_pressure_mb": peak["pressure_mb"],
                "ibtracs_lat": peak["lat"],
                "ibtracs_lon": peak["lon"],
                "pass": abs(float(peak["wind_kt"]) - 155.0) <= 5.0,
            },
            {
                "check": "Honduras landfall intensity",
                "nhc_report_reference": NHC_MITCH_TCR_URL,
                "nhc_value": "Morning of 1998-10-29, about 70 n mi east of La Ceiba; 70 kt and 987 mb at 1200 UTC in Table 1",
                "ibtracs_time": landfall["iso_time"],
                "ibtracs_wind_kt": landfall["wind_kt"],
                "ibtracs_pressure_mb": landfall["pressure_mb"],
                "ibtracs_lat": landfall["lat"],
                "ibtracs_lon": landfall["lon"],
                "pass": abs(float(landfall["wind_kt"]) - 70.0) <= 10.0,
            },
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process Hurricane Mitch's IBTrACS track.")
    parser.add_argument("--ibtracs", type=Path, default=DEFAULT_IBTRACS_CSV)
    args = parser.parse_args(argv)

    ensure_project_dirs()
    if not args.ibtracs.exists():
        raise FileNotFoundError(f"Missing IBTrACS CSV: {args.ibtracs}. Run scripts/01_download_data.py first.")
    track = process_mitch_track(args.ibtracs)
    csv_path = output_path(PROCESSED_DIR / "mitch_ibtracs_track.csv")
    track.to_csv(csv_path, index=False)
    save_geojson(track)
    validation = validation_table(track)
    validation.to_csv(output_path(PROCESSED_DIR / "mitch_track_validation.csv"), index=False)
    print(f"Wrote {len(track)} Mitch track rows to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
