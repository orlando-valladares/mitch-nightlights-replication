from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_config import DEFAULT_NTL_CSV, PROCESSED_DIR, RAW_DIR, ensure_project_dirs, output_path, resolve_path
from pipeline_utils import ensure_muni_fields, first_existing_column, read_table, safe_bool_int, to_numeric, zscore


def discover_ntl(explicit: Path | None) -> Path:
    if explicit is not None:
        explicit = resolve_path(explicit)
        if explicit and explicit.exists():
            return explicit
        raise FileNotFoundError(f"NTL file not found: {explicit}")
    if DEFAULT_NTL_CSV.exists():
        return DEFAULT_NTL_CSV
    patterns = ["*ntl*.csv", "*NTL*.csv", "*dmsp*.csv", "*DMSP*.csv", "*stable*.csv", "*.dta"]
    for pattern in patterns:
        matches = sorted(RAW_DIR.rglob(pattern)) if RAW_DIR.exists() else []
        if matches:
            return matches[0]
    raise FileNotFoundError("No NTL CSV/DTA found. Pass --ntl path/to/nightlights.csv.")


def standardize_ntl(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_muni_fields(df)
    year_col = first_existing_column(df, ["year", "YEAR"])
    sat_col = first_existing_column(df, ["satellite", "SATELLITE", "sat", "image_id"])
    stable_col = first_existing_column(df, ["stable_sum", "sum", "stable_lights_sum"])
    if year_col is None or sat_col is None or stable_col is None:
        raise ValueError("NTL table must include year, satellite, and stable_sum columns or recognizable equivalents.")
    df["year"] = to_numeric(df[year_col]).astype("Int64")
    df["satellite"] = df[sat_col].astype(str)
    df["stable_sum"] = to_numeric(df[stable_col])
    if "muni_key" not in df.columns:
        raise ValueError("Could not infer a municipality key from the NTL table. Add muni_key or ADM0/ADM1/ADM2 codes.")
    return df


def load_exposure(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, low_memory=False)
    df = ensure_muni_fields(df)
    return df


def merge_by_best_key(left: pd.DataFrame, right: pd.DataFrame | None, suffix: str) -> pd.DataFrame:
    if right is None or right.empty:
        return left
    left = ensure_muni_fields(left)
    right = ensure_muni_fields(right)
    right_cols = [c for c in right.columns if c not in {"country_name", "department_name", "municipality_name"}]
    right = right[right_cols].drop_duplicates(subset=["muni_key"] if "muni_key" in right.columns else None)
    if "muni_key" in left.columns and "muni_key" in right.columns:
        return left.merge(right, on="muni_key", how="left", suffixes=("", suffix))
    name_keys = ["country_name_norm", "dept_name_norm", "muni_name_norm"]
    if all(k in left.columns for k in name_keys) and all(k in right.columns for k in name_keys):
        return left.merge(right, on=name_keys, how="left", suffixes=("", suffix))
    return left


def add_treatments(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["year"] = to_numeric(panel["year"]).astype("Int64")
    panel["post_1998"] = panel["year"].ge(1999).astype(int)
    for col in ["any_r64", "any_r50", "any_r34"]:
        if col in panel.columns:
            panel[f"treated_{col[-3:]}"] = safe_bool_int(panel[col])
        else:
            panel[f"treated_{col[-3:]}"] = 0
    if "max_estimated_wind_kt" in panel.columns and panel["max_estimated_wind_kt"].notna().any():
        panel["wind_exposure_metric"] = to_numeric(panel["max_estimated_wind_kt"])
        panel["wind_exposure_metric_source"] = "max_estimated_wind_kt"
    else:
        wind = to_numeric(panel.get("nearest_track_wind_kt", pd.Series(np.nan, index=panel.index)))
        dist = to_numeric(panel.get("centroid_min_distance_to_track_km", pd.Series(np.nan, index=panel.index)))
        panel["distance_weighted_wind_kt"] = wind / (1.0 + dist / 50.0)
        panel["wind_exposure_metric"] = panel["distance_weighted_wind_kt"]
        panel["wind_exposure_metric_source"] = "distance_weighted_wind_kt"

    rain_metric = None
    for candidate in ["mean_rainfall_mm", "area_weighted_rainfall_mm", "p90_rainfall_mm"]:
        if candidate in panel.columns and panel[candidate].notna().any():
            rain_metric = candidate
            break
    panel["rain_exposure_metric"] = to_numeric(panel[rain_metric]) if rain_metric else np.nan
    panel["rain_exposure_metric_source"] = rain_metric or ""

    muni_key = "muni_key" if "muni_key" in panel.columns else None
    exposure_unit = panel.drop_duplicates(subset=[muni_key] if muni_key else None).copy()
    wind_q75 = exposure_unit["wind_exposure_metric"].quantile(0.75)
    rain_q75 = exposure_unit["rain_exposure_metric"].quantile(0.75)
    panel["high_wind"] = panel["wind_exposure_metric"].ge(wind_q75).fillna(False).astype(int)
    panel["high_rain"] = panel["rain_exposure_metric"].ge(rain_q75).fillna(False).astype(int)

    if muni_key:
        scores = exposure_unit[[muni_key, "wind_exposure_metric", "rain_exposure_metric"]].copy()
        scores["combined_exposure_z"] = zscore(scores["wind_exposure_metric"]) + zscore(scores["rain_exposure_metric"])
        panel = panel.drop(columns=["combined_exposure_z"], errors="ignore").merge(
            scores[[muni_key, "combined_exposure_z"]],
            on=muni_key,
            how="left",
        )
    else:
        panel["combined_exposure_z"] = zscore(panel["wind_exposure_metric"]) + zscore(panel["rain_exposure_metric"])
    return panel


def write_crosswalk(panel: pd.DataFrame) -> None:
    cols = [
        c
        for c in [
            "muni_key",
            "country_name",
            "department_name",
            "municipality_name",
            "country_name_norm",
            "dept_name_norm",
            "muni_name_norm",
        ]
        if c in panel.columns
    ]
    if cols:
        panel[cols].drop_duplicates().to_csv(output_path(PROCESSED_DIR / "municipality_ntl_crosswalk.csv"), index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge NTL panel with Mitch exposure variables.")
    parser.add_argument("--ntl", type=Path, default=None, help="Nightlights CSV or Stata DTA.")
    parser.add_argument("--distance", type=Path, default=PROCESSED_DIR / "municipality_mitch_distance_exposure.csv")
    parser.add_argument("--swath", type=Path, default=PROCESSED_DIR / "municipality_mitch_wind_swath_exposure.csv")
    parser.add_argument("--rainfall", type=Path, default=PROCESSED_DIR / "municipality_mitch_rainfall_exposure.csv")
    parser.add_argument("--max-wind", type=Path, default=PROCESSED_DIR / "municipality_mitch_max_wind.csv")
    args = parser.parse_args(argv)

    ensure_project_dirs()
    ntl_path = discover_ntl(args.ntl)
    panel = standardize_ntl(read_table(ntl_path))
    base_rows = len(panel)
    for path, suffix in [
        (args.distance, "_distance"),
        (args.swath, "_swath"),
        (args.rainfall, "_rainfall"),
        (args.max_wind, "_maxwind"),
    ]:
        panel = merge_by_best_key(panel, load_exposure(path), suffix)

    panel = add_treatments(panel)
    out_path = output_path(PROCESSED_DIR / "municipality_ntl_mitch_panel.csv")
    panel.to_csv(out_path, index=False)
    write_crosswalk(panel)
    print(f"Wrote merged NTL/exposure panel with {len(panel)} rows from {base_rows} NTL rows: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
