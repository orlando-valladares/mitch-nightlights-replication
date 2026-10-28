from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pyproj import Geod
from shapely.geometry import Polygon
from shapely.ops import unary_union

from pipeline_config import DEFAULT_EBTRK_TXT, PROCESSED_DIR, output_path
from pipeline_utils import to_numeric


ROOT = Path(__file__).resolve().parents[2]
WORKING = ROOT / "working"
OUT = ROOT / "out"
PAPER_ROOT = ROOT / "paper" / "Paper_Figures"
PAPER_LEGACY = PAPER_ROOT / "legacy"
AREA_CRS = "EPSG:6933"
GEOD = Geod(ellps="WGS84")
PRE_MITCH_NTL_MEDIAN = 101.79

THRESHOLDS = ["r64", "r50", "r34"]
THRESHOLD_LABELS = {"r34": "34 kt", "r50": "50 kt", "r64": "64 kt"}
EBTRK_TREAT_PREFIX = "ebtrk_treat50"
QUADRANTS = ["NE", "SE", "NW", "SW"]
BUNDLES = [("ALL", ["NE", "SE", "NW", "SW"])]
BUNDLE_LABELS = {"ALL": "All quadrants"}
EVENT_TABLE_YEARS = list(range(1995, 2005))
TABLE_EVENT_PERIODS = [
    (1992, 1993),
    (1994, 1995),
    (1996, 1997),
    (1998, 1999),
    (2000, 2001),
    (2002, 2003),
    (2004, 2005),
    (2006, 2007),
]
TABLE_OUTPUT_PERIODS = TABLE_EVENT_PERIODS + [(2008, 2009)]
EVENT_PERIODS = TABLE_EVENT_PERIODS + [
    (2008, 2009),
    (2010, 2011),
    (2012, 2013),
]
REFERENCE_PERIOD = (1996, 1997)
SELECTED_COUNTRIES = {"Belize", "Guatemala", "El Salvador", "Honduras", "Nicaragua"}
EXPANDED_OUT = OUT / "Expanded version"
EXPANDED_OVERLEAF = PAPER_ROOT / "extended"
MAHAJAN_APPENDIX_PDF_CANDIDATES = [
    ROOT
    / "Mahajan, Parag; Dean Yang - Appendix, Taken by Storm; Hurricanes, Migrant Networks, and US Immigration (2020, American Economic Journal Applied Economics).pdf",
    WORKING / "resources" / "Mahajan; Yang - Appendix, Taken by Storm, Hurricanes, Migrant Networks and US Immigration (2020, AEJ Applied).pdf",
]


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


def ensure_dirs() -> None:
    for path in [
        OUT / "data" / "tables" / "assignment",
        OUT / "data" / "tables" / "besttrack",
        OUT / "data" / "figures",
        OUT / "results" / "tables",
        OUT / "results" / "figures",
        OUT / "paper_figures",
        PAPER_ROOT,
        PAPER_LEGACY,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def write_text_outputs(paths: list[Path], text: str) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


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
            radii: list[str] = []
            for group in [radii_text[0:12], radii_text[13:25], radii_text[26:38]]:
                radii.extend(group[i : i + 3].strip() for i in range(0, 12, 3))
            rows.append([*first_fields[:12], *radii, storm_type, distance_to_land, source_code])
    df = pd.DataFrame(rows, columns=EBTRK_COLUMNS)
    numeric_cols = [c for c in EBTRK_COLUMNS if c not in {"storm_id", "storm_name", "mmddhh", "storm_type", "structure_source_code"}]
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


def load_mitch_ebtrk() -> pd.DataFrame:
    path = DEFAULT_EBTRK_TXT
    df = parse_ebtrk(path)
    out = df.loc[df["year"].eq(1998) & df["storm_name"].eq("MITCH")].dropna(subset=["lat", "lon", "iso_time"])
    out = out.sort_values("iso_time").reset_index(drop=True)
    if out.empty:
        raise RuntimeError("No Hurricane Mitch rows found in EBTRK.")
    out.to_csv(output_path(PROCESSED_DIR / "mitch_ebtrk_wind_radii.csv"), index=False)
    return out


def sector_polygon(lon: float, lat: float, radius_nm: float, quadrant: str) -> Polygon | None:
    if not np.isfinite(radius_nm) or radius_nm <= 0:
        return None
    starts = {"NE": 0.0, "SE": 90.0, "SW": 180.0, "NW": 270.0}
    start = starts[quadrant]
    bearings = np.linspace(start, start + 90.0, 22)
    arc = []
    for bearing in bearings:
        x, y, _ = GEOD.fwd(float(lon), float(lat), float(bearing), float(radius_nm) * 1852.0)
        arc.append((x, y))
    poly = Polygon([(float(lon), float(lat)), *arc, (float(lon), float(lat))])
    return poly if poly.is_valid and not poly.is_empty else None


def build_quadrant_swaths(ebtrk: pd.DataFrame) -> dict[tuple[str, str], object]:
    swaths: dict[tuple[str, str], object] = {}
    for threshold in THRESHOLDS:
        for quadrant in QUADRANTS:
            col = f"{threshold}_{quadrant.lower()}_nm"
            pieces = []
            for _, row in ebtrk.loc[pd.to_numeric(ebtrk[col], errors="coerce").fillna(0).gt(0)].iterrows():
                piece = sector_polygon(row["lon"], row["lat"], row[col], quadrant)
                if piece is not None:
                    pieces.append(piece)
            if pieces:
                swaths[(threshold, quadrant)] = unary_union(pieces)
    return swaths


def build_bundle_swaths(swaths: dict[tuple[str, str], object]) -> dict[tuple[str, str], object]:
    out: dict[tuple[str, str], object] = {}
    for threshold in THRESHOLDS:
        for bundle, quadrants in BUNDLES:
            pieces = [swaths[(threshold, q)] for q in quadrants if (threshold, q) in swaths]
            if pieces:
                out[(threshold, bundle)] = unary_union(pieces)
    return out


def load_municipalities() -> gpd.GeoDataFrame:
    path = PROCESSED_DIR / "did_dashboard" / "gaul_name_matched_municipalities_analytical.geojson"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}.")
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)


def add_ebtrk_exposures(munis: gpd.GeoDataFrame, bundle_swaths: dict[tuple[str, str], object]) -> gpd.GeoDataFrame:
    out = munis.copy()
    metric = out.to_crs(AREA_CRS)
    areas = metric.geometry.area.replace(0, np.nan)
    for threshold in THRESHOLDS:
        for bundle, _ in BUNDLES:
            col = f"ebtrk_share_{threshold}_{bundle.lower()}"
            geom = bundle_swaths.get((threshold, bundle))
            if geom is None:
                shares = pd.Series(0.0, index=out.index)
            else:
                swath = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(AREA_CRS).iloc[0]
                shares = metric.geometry.intersection(swath).area / areas
            out[col] = shares.fillna(0).clip(0, 1).round(6)
            out[f"ebtrk_treat50_{threshold}_{bundle.lower()}"] = out[col].ge(0.5).astype(int)
            out[f"ebtrk_any_{threshold}_{bundle.lower()}"] = out[col].gt(0).astype(int)
    return out


def audited_ebtrk_bundle_exposures() -> pd.DataFrame:
    path = OUT / "data" / "tables" / "besttrack" / "mitch_ebtrk_quadrant_municipality_exposure.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing audited quadrant exposure table: {path}")
    long = pd.read_csv(path)
    out_keys = pd.DataFrame({"muni_key": sorted(long["muni_key"].dropna().unique())})
    rows = {"muni_key": out_keys["muni_key"]}
    for threshold in THRESHOLDS:
        wide = (
            long.loc[long["threshold"].eq(threshold)]
            .pivot_table(index="muni_key", columns="quadrant", values="share_area", aggfunc="max")
            .reindex(columns=QUADRANTS)
            .fillna(0.0)
        )
        for bundle, quadrants in BUNDLES:
            share = wide.reindex(columns=quadrants).max(axis=1).fillna(0.0)
            col = f"ebtrk_share_{threshold}_{bundle.lower()}"
            rows[col] = out_keys["muni_key"].map(share).fillna(0.0).round(6)
            rows[f"ebtrk_treat50_{threshold}_{bundle.lower()}"] = rows[col].ge(0.5).astype(int)
            rows[f"ebtrk_any_{threshold}_{bundle.lower()}"] = rows[col].gt(0).astype(int)
    return pd.DataFrame(rows)


def attach_audited_ebtrk_exposures(munis: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    exposure = audited_ebtrk_bundle_exposures()
    if "geometry_source_id" in munis.columns:
        exposure = exposure.rename(columns={"muni_key": "geometry_source_id"})
        out = munis.merge(exposure, on="geometry_source_id", how="left")
        join_key = "geometry_source_id"
    else:
        out = munis.merge(exposure, on="muni_key", how="left")
        join_key = "muni_key"
    exposure_cols = [c for c in exposure.columns if c != join_key]
    for col in exposure_cols:
        out[col] = out[col].fillna(0.0)
        if "_treat50_" in col or "_any_" in col:
            out[col] = out[col].astype(int)
    return out


def representative_latlon(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    reps = gdf.to_crs("EPSG:4326").representative_point()
    return pd.DataFrame({"muni_key": gdf["muni_key"], "yang_rep_lon": reps.x, "yang_rep_lat": reps.y})


def haversine_matrix(lat: np.ndarray, lon: np.ndarray, glat: np.ndarray, glon: np.ndarray) -> np.ndarray:
    r = 6371.0088
    lat1 = np.radians(lat)[:, None]
    lon1 = np.radians(lon)[:, None]
    lat2 = np.radians(glat)[None, :]
    lon2 = np.radians(glon)[None, :]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0, 1 - a)))


def add_mahajan_exposure(munis: pd.DataFrame) -> pd.DataFrame:
    grid = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "yang_parag_mitch_grid.csv")
    grid = grid.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    for col in ["x_gjst", "pwind", "dist", "pradius34"]:
        grid[col] = pd.to_numeric(grid[col], errors="coerce").fillna(0.0)
    grid["is_original_treated"] = grid["is_original_treated"].astype(str).str.lower().isin(["true", "1"])

    lat = munis["yang_rep_lat"].to_numpy(float)
    lon = munis["yang_rep_lon"].to_numpy(float)
    glat = grid["latitude"].to_numpy(float)
    glon = grid["longitude"].to_numpy(float)
    d = haversine_matrix(lat, lon, glat, glon)
    nearest = d.argmin(axis=1)
    nearest_grid = grid.iloc[nearest].reset_index(drop=True)
    munis["mp_nearest_grid_id"] = nearest_grid["grid_id"].to_numpy()
    munis["mp_nearest_grid_km"] = d[np.arange(len(munis)), nearest].round(6)
    munis["mp_binary"] = nearest_grid["is_original_treated"].astype(int).to_numpy()
    munis["mp_x_gjst"] = nearest_grid["x_gjst"].to_numpy(float)
    munis["mp_pwind"] = nearest_grid["pwind"].to_numpy(float)
    munis["mp_grid_pop"] = pd.to_numeric(nearest_grid["grid_pop"], errors="coerce").fillna(0.0).to_numpy(float)

    treated = grid.loc[grid["is_original_treated"]].reset_index(drop=True)
    control = grid.loc[~grid["is_original_treated"]].reset_index(drop=True)
    dt = haversine_matrix(lat, lon, treated["latitude"].to_numpy(float), treated["longitude"].to_numpy(float))
    dc = haversine_matrix(lat, lon, control["latitude"].to_numpy(float), control["longitude"].to_numpy(float))
    munis["yang_nearest_treated_grid_km"] = dt.min(axis=1).round(6)
    munis["yang_nearest_control_grid_km"] = dc.min(axis=1).round(6)
    munis["yang_default_treated"] = (munis["yang_nearest_treated_grid_km"] < munis["yang_nearest_control_grid_km"]).astype(int)
    return munis


def add_pre_lights(munis: pd.DataFrame) -> pd.DataFrame:
    panel = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    panel["stable_sum"] = pd.to_numeric(panel["stable_sum"], errors="coerce")
    pre = panel.loc[panel["year"].le(1997)].groupby("muni_key", as_index=False)["stable_sum"].mean()
    pre = pre.rename(columns={"stable_sum": "pre_mean_stable_sum"})
    return munis.drop(columns=[c for c in ["pre_mean_stable_sum"] if c in munis.columns]).merge(pre, on="muni_key", how="left")


def add_state_impacts(munis: pd.DataFrame) -> pd.DataFrame:
    state_path = OUT / "data" / "tables" / "assignment" / "assignment_state_impacts.csv"
    if not state_path.exists():
        return munis
    states = pd.read_csv(state_path)
    keep = ["state_key", "impact_deaths", "impact_population", "deaths_per_capita", "death_score", "has_death_data"]
    states = states[[c for c in keep if c in states.columns]]
    return munis.merge(states, on="state_key", how="left")



def add_expanded_exposure_flags(out: pd.DataFrame) -> pd.DataFrame:
    selected = out["country_name"].isin(SELECTED_COUNTRIES)
    rain = pd.to_numeric(out.loc[selected, "rain_max_daily_anomaly_mm"], errors="coerce").dropna()
    rain_cut = float(rain.quantile(0.90)) if len(rain) else np.nan
    if np.isfinite(rain_cut):
        out["chirps_max_anomaly_top10"] = (selected & pd.to_numeric(out["rain_max_daily_anomaly_mm"], errors="coerce").ge(rain_cut)).astype(int)
    else:
        out["chirps_max_anomaly_top10"] = 0
    out["chirps_max_anomaly_top10_cutoff_mm"] = rain_cut
    # Backward-compatible column name; this is now top-decile CHIRPS rainfall only,
    # not interacted with the 50 kt wind treatment.
    out["rain50_chirps_top10"] = out["chirps_max_anomaly_top10"]
    out["rain50_chirps_top10_cutoff_mm"] = rain_cut

    states = out.loc[selected, ["state_key", "deaths_per_capita", "has_death_data"]].drop_duplicates("state_key").copy()
    death_vals = pd.to_numeric(states.loc[states["has_death_data"].eq(1), "deaths_per_capita"], errors="coerce").dropna()
    death_cut = float(death_vals.quantile(0.90)) if len(death_vals) else np.nan
    top_states = set(states.loc[pd.to_numeric(states["deaths_per_capita"], errors="coerce").ge(death_cut), "state_key"]) if np.isfinite(death_cut) else set()
    out["death_pc_top10_state"] = out["state_key"].isin(top_states).astype(int)
    out["death_pc_top10_state_cutoff"] = death_cut
    return out

def build_assignment(munis_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    reps = representative_latlon(munis_gdf)
    cols = [
        "muni_key",
        "country_name",
        "department_name",
        "municipality_name",
        "min_distance_to_track_km",
        "centroid_min_distance_to_track_km",
        "nearest_track_wind_kt",
        "nearest_track_pressure_mb",
        "max_track_wind_within_50km",
        "max_track_wind_within_100km",
        "max_track_wind_within_150km",
        "max_track_wind_within_200km",
        "rain_total_mean_mm",
        "rain_total_anomaly_mm",
        "rain_max_daily_mean_mm",
        "rain_max_daily_anomaly_mm",
    ]
    keep = [c for c in cols if c in munis_gdf.columns]
    out = pd.DataFrame(munis_gdf[keep])
    out["state_key"] = out["country_name"].astype(str) + "|" + out["department_name"].astype(str)
    out = out.merge(reps, on="muni_key", how="left")
    for threshold in THRESHOLDS:
        for bundle, _ in BUNDLES:
            for prefix in ["ebtrk_share", "ebtrk_treat50", "ebtrk_any"]:
                col = f"{prefix}_{threshold}_{bundle.lower()}"
                out[col] = munis_gdf[col].to_numpy()
    for threshold in THRESHOLDS:
        out[f"share_area_{threshold}"] = munis_gdf[f"ebtrk_share_{threshold}_all"].to_numpy()
        out[f"treated50_{threshold}"] = munis_gdf[f"ebtrk_treat50_{threshold}_all"].to_numpy()
        out[f"any_{threshold}"] = munis_gdf[f"ebtrk_any_{threshold}_all"].to_numpy()
    out["best_default_score"] = out["ebtrk_share_r64_all"]
    out = add_pre_lights(out)
    out = add_mahajan_exposure(out)
    out = add_state_impacts(out)
    out["in_selected_country"] = out["country_name"].isin(SELECTED_COUNTRIES).astype(int)
    no_filter = out.loc[out["in_selected_country"].eq(1), "mp_x_gjst"]
    mean = no_filter.mean()
    sd = no_filter.std(ddof=1)
    out["mp_x_gjst_z_nofilter"] = (out["mp_x_gjst"] - mean) / sd if sd > 0 else 0.0
    filt = out.loc[out["in_selected_country"].eq(1) & out["pre_mean_stable_sum"].notna() & out["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN), "mp_x_gjst"]
    fmean = filt.mean()
    fsd = filt.std(ddof=1)
    out["mp_x_gjst_z_prefilter"] = (out["mp_x_gjst"] - fmean) / fsd if fsd > 0 else 0.0
    out = add_expanded_exposure_flags(out)
    out.to_csv(OUT / "data" / "tables" / "assignment" / "assignment_municipalities.csv", index=False)
    return out


def fmt(x: float | int | str, digits: int = 3) -> str:
    if isinstance(x, str):
        return x
    if pd.isna(x):
        return ""
    if abs(float(x) - round(float(x))) < 1e-9 and abs(float(x)) >= 10:
        return f"{int(round(float(x))):,}"
    return f"{float(x):.{digits}f}"


def tex_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("$", r"\$")
        .replace("#", r"\#")
        .replace("_", r"\_")
    )


def stat_summary(vals: pd.Series) -> dict[str, float]:
    vals = pd.to_numeric(vals, errors="coerce").dropna()
    if len(vals) == 0:
        return {"mean": np.nan, "sd": np.nan, "p10": np.nan, "p50": np.nan, "p90": np.nan, "count": 0}
    return {
        "mean": float(vals.mean()),
        "sd": float(vals.std(ddof=1)) if len(vals) > 1 else np.nan,
        "p10": float(vals.quantile(0.10)),
        "p50": float(vals.quantile(0.50)),
        "p90": float(vals.quantile(0.90)),
        "count": int(len(vals)),
    }


def summary_data_row(panel: str, section: str, measure: str, vals: pd.Series, count: int | None = None) -> dict[str, object]:
    row: dict[str, object] = {"panel": panel, "section": section, "measure": measure}
    row.update(stat_summary(vals))
    row["count"] = count if count is not None else np.nan
    return row


def summary_count_row(panel: str, section: str, measure: str, count: int) -> dict[str, object]:
    return {
        "panel": panel,
        "section": section,
        "measure": measure,
        "mean": np.nan,
        "sd": np.nan,
        "p10": np.nan,
        "p50": np.nan,
        "p90": np.nan,
        "count": count,
        "cover100": np.nan,
        "cover75": np.nan,
        "cover50": np.nan,
        "cover25": np.nan,
    }


def summary_coverage_row(panel: str, threshold: str, vals: pd.Series) -> dict[str, object]:
    vals = pd.to_numeric(vals, errors="coerce").fillna(0)
    return {
        "panel": panel,
        "section": "Extended Best Track wind swath coverage",
        "measure": f"{THRESHOLD_LABELS[threshold]} winds and above",
        "mean": np.nan,
        "sd": np.nan,
        "p10": np.nan,
        "p50": np.nan,
        "p90": np.nan,
        "count": np.nan,
        "cover100": int(vals.ge(0.999).sum()),
        "cover75": int(vals.ge(0.75).sum()),
        "cover50": int(vals.ge(0.50).sum()),
        "cover25": int(vals.ge(0.25).sum()),
    }


def summary_tex_number(value: object, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return ""
    x = float(value)
    if digits == 0:
        return f"{int(round(x)):,}"
    if abs(x) < 1e-12:
        return "0"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if abs(x) >= 100:
        return f"{x:,.1f}"
    if abs(x) >= 10:
        return f"{x:,.2f}"
    if abs(x) >= 1:
        return f"{x:,.3f}"
    return f"{x:.{digits}f}"



def build_summary_tables(assignment: pd.DataFrame) -> pd.DataFrame:
    sample = assignment.loc[assignment["in_selected_country"].eq(1)].copy()
    pre = sample.loc[sample["pre_mean_stable_sum"].notna() & sample["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
    ntl = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    ntl["stable_sum"] = pd.to_numeric(ntl["stable_sum"], errors="coerce")
    ntl = ntl.merge(sample[["muni_key", "pre_mean_stable_sum"]].rename(columns={"pre_mean_stable_sum": "sample_pre_mean"}), on="muni_key", how="inner")
    ntl_pre = ntl.loc[ntl["sample_pre_mean"].ge(PRE_MITCH_NTL_MEDIAN)].copy()

    def row(panel, section, measure, vals, source="", geography="Municipality", treated="", treated_filter=""):
        stats = stat_summary(vals)
        return {"panel": panel, "section": section, "measure": measure, "source": source, "geography": geography, "treated": treated, "treated_filter": treated_filter, **stats}

    rows = []
    for panel_label, ntl_sub in [("Full retained sample", ntl), ("Pre-Mitch NTL at or above median (101.79)", ntl_pre)]:
        muni_n = ntl_sub["muni_key"].nunique()
        rows.append(row(panel_label, "Dependent Variable: Nightlights", "DMSP-OLS stable lights, 1998", ntl_sub.loc[ntl_sub["year"].eq(1998), "stable_sum"], source="DMSP-OLS", geography=f"{muni_n:,} municipalities"))
        rows.append(row(panel_label, "Dependent Variable: Nightlights", "DMSP-OLS stable lights, all years", ntl_sub["stable_sum"], source="DMSP-OLS", geography=f"{muni_n:,} municipalities"))

    for threshold in THRESHOLDS:
        label = f"{THRESHOLD_LABELS[threshold]} winds"
        vals = pd.to_numeric(sample[f"ebtrk_share_{threshold}_all"], errors="coerce").fillna(0)
        rows.append(row("Full retained sample", "Independent Variable: Mitch Exposure Measures", label, vals, source="Extended Best Track", treated=int(sample[f"{EBTRK_TREAT_PREFIX}_{threshold}_all"].sum()), treated_filter=int(pre[f"{EBTRK_TREAT_PREFIX}_{threshold}_all"].sum())))
        rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", f"{THRESHOLD_LABELS[threshold]} area share", vals, source="Extended Best Track", treated="", treated_filter=""))
        positive = vals.loc[vals.gt(0)]
        rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", f"{THRESHOLD_LABELS[threshold]} area share, if > 0", positive, source="Extended Best Track", geography=f"{len(positive):,} positive"))
    rows.append(row("Full retained sample", "Independent Variable: Mitch Exposure Measures", "Top 10% max rainfall anomaly", sample["rain_max_daily_anomaly_mm"], source="CHIRPS", treated=int(sample["chirps_max_anomaly_top10"].sum()), treated_filter=int(pre["chirps_max_anomaly_top10"].sum())))
    rows.append(row("Full retained sample", "Independent Variable: Mitch Exposure Measures", "Top 10% deaths per capita (state)", sample.drop_duplicates("state_key")["deaths_per_capita"], source="Government Reports", geography="Department/state", treated=int(sample["death_pc_top10_state"].sum()), treated_filter=int(pre["death_pc_top10_state"].sum())))
    rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", "CHIRPS max rainfall anomaly", sample["rain_max_daily_anomaly_mm"], source="CHIRPS"))
    rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", "Deaths per capita (state)", sample.drop_duplicates("state_key")["deaths_per_capita"], source="Government Reports", geography="Department/state"))
    death_pos = sample.drop_duplicates("state_key").loc[lambda d: pd.to_numeric(d["deaths_per_capita"], errors="coerce").gt(0), "deaths_per_capita"]
    rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", "Deaths per capita (state), if > 0", death_pos, source="Government Reports", geography=f"{len(death_pos):,} positive departments"))
    rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", "Mahajan-Parag point exposure index", sample["mp_x_gjst"], source="Mahajan-Parag"))
    mp_pos = sample.loc[sample["mp_x_gjst"].gt(0), "mp_x_gjst"]
    rows.append(row("Full retained sample", "Independent Variable: Continuous Mitch Exposure Measures", "Mahajan-Parag point exposure index, if > 0", mp_pos, source="Mahajan-Parag", geography=f"{len(mp_pos):,} positive"))

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "data" / "tables" / "assignment" / "exposure_summary_main.csv", index=False)
    out.loc[out["section"].str.contains("Mitch Exposure", na=False)].to_csv(OUT / "data" / "tables" / "assignment" / "exposure_summary_ebtrk_binary.csv", index=False)
    out.loc[out["measure"].str.contains("Mahajan-Parag", na=False)].to_csv(OUT / "data" / "tables" / "assignment" / "exposure_summary_mp_continuous.csv", index=False)

    def num(v, digits=3):
        return summary_tex_number(v, digits)

    lines = [r"\begin{tabular}{llrrrrrr}", r"\toprule", r"Panel / Measure & Source & Mean & SD & P10 & P50 & P90 & N \\", r"\midrule"]
    for section in ["Dependent Variable: Nightlights", "Independent Variable: Mitch Exposure Measures", "Independent Variable: Continuous Mitch Exposure Measures"]:
        lines.append(rf"\multicolumn{{8}}{{l}}{{\emph{{{tex_escape(section)}}}}} \\")
        sub = out.loc[out["section"].eq(section)]
        for _, r in sub.iterrows():
            n_text = r["geography"] if isinstance(r["geography"], str) and r["geography"] else num(r["count"], 0)
            lines.append(" & ".join([tex_escape(r["measure"]), tex_escape(r.get("source", "")), num(r["mean"], 6), num(r["sd"], 6), num(r["p10"], 6), num(r["p50"], 6), num(r["p90"], 6), tex_escape(n_text)]) + r" \\")
        lines.append(r"\addlinespace[0.35em]")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    tex = "\n".join(lines)
    write_text_outputs([
        OUT / "paper_figures" / "table_exposure_summary_main.tex",
        PAPER_LEGACY / "table_exposure_summary_main.tex",
    ], tex)
    write_expanded_summary_table(assignment, ntl)
    return out


def _expanded_summary_row(measure: str, source: str, unit: str, values: pd.Series, **extra: object) -> dict:
    stats = stat_summary(pd.to_numeric(values, errors="coerce"))
    return {"measure": measure, "source": source, "unit": unit, **stats, **extra}


def write_expanded_summary_table(assignment: pd.DataFrame, ntl: pd.DataFrame | None = None) -> None:
    sample = assignment.loc[assignment["in_selected_country"].eq(1)].copy()
    if ntl is None:
        ntl = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
        ntl["stable_sum"] = pd.to_numeric(ntl["stable_sum"], errors="coerce")
        ntl = ntl.merge(sample[["muni_key", "pre_mean_stable_sum"]].rename(columns={"pre_mean_stable_sum": "sample_pre_mean"}), on="muni_key", how="inner")
    ntl = ntl.copy()
    ntl["log_ntl"] = np.log1p(pd.to_numeric(ntl["stable_sum"], errors="coerce"))
    ntl_pre = ntl.loc[pd.to_numeric(ntl["sample_pre_mean"], errors="coerce").ge(PRE_MITCH_NTL_MEDIAN)].copy()

    dep_rows = []
    for label, frame in [("All retained municipalities", ntl), ("Pre-Mitch NTL at or above median (101.79)", ntl_pre)]:
        dep_rows.append(_expanded_summary_row("Stable lights, all years", "DMSP-OLS", label, frame["stable_sum"], units=frame["muni_key"].nunique(), obs=len(frame)))
        dep_rows.append(_expanded_summary_row("Stable lights, 1998", "DMSP-OLS", label, frame.loc[frame["year"].eq(1998), "stable_sum"], units=frame.loc[frame["year"].eq(1998), "muni_key"].nunique(), obs=int(frame["year"].eq(1998).sum())))
        dep_rows.append(_expanded_summary_row("log(1 + stable lights), all years", "DMSP-OLS", label, frame["log_ntl"], units=frame["muni_key"].nunique(), obs=len(frame)))

    indep_rows = []
    for threshold in THRESHOLDS:
        share_col = f"ebtrk_share_{threshold}_all"
        share = pd.to_numeric(sample[share_col], errors="coerce").fillna(0)
        for cutoff in [1.00, 0.75, 0.50, 0.25]:
            flags = share.ge(cutoff)
            treated_depts = sample.loc[flags, "state_key"].nunique()
            indep_rows.append(_expanded_summary_row(f"{THRESHOLD_LABELS[threshold]} area coverage >= {int(cutoff * 100)}%", "Extended Best Track", "Municipality share", share, treated_munis=int(flags.sum()), treated_depts=int(treated_depts)))

    rainfall = pd.to_numeric(sample["rain_max_daily_anomaly_mm"], errors="coerce")
    rain_flags = sample["chirps_max_anomaly_top10"].eq(1)
    indep_rows.append(_expanded_summary_row("CHIRPS max rainfall anomaly", "CHIRPS", "mm anomaly", rainfall, treated_munis=int(rain_flags.sum()), treated_depts=int(sample.loc[rain_flags, "state_key"].nunique())))
    indep_rows.append(_expanded_summary_row("Average CHIRPS rainfall anomaly", "CHIRPS", "Mean over sample", pd.Series([rainfall.mean()]), treated_munis="", treated_depts=""))

    states = sample.drop_duplicates("state_key").copy()
    deaths = pd.to_numeric(states["deaths_per_capita"], errors="coerce")
    death_flags = states["death_pc_top10_state"].eq(1)
    indep_rows.append(_expanded_summary_row("Deaths per capita", "Government reports", "All departments/states", deaths, treated_munis="", treated_depts=int(death_flags.sum())))
    indep_rows.append(_expanded_summary_row("Deaths per capita, if > 0", "Government reports", "Positive departments/states", deaths.loc[deaths.gt(0)], treated_munis="", treated_depts=int(death_flags.sum())))

    dep = pd.DataFrame(dep_rows)
    indep = pd.DataFrame(indep_rows)
    dep.to_csv(OUT / "data" / "tables" / "assignment" / "expanded_summary_dependent.csv", index=False)
    indep.to_csv(OUT / "data" / "tables" / "assignment" / "expanded_summary_independent.csv", index=False)

    def num(v, digits=3):
        return summary_tex_number(v, digits)

    def stat_cells(r: pd.Series) -> list[str]:
        return [num(r[k], 6) for k in ["mean", "sd", "p10", "p50", "p90"]]

    row_end = " " + chr(92) * 2
    dep_lines = [r"\begin{tabular}{lllrrrrrr}", r"\toprule", "Outcome & Source & Sample & Mean & SD & P10 & P50 & P90 & Obs" + row_end, r"\midrule"]
    for _, r in dep.iterrows():
        dep_lines.append(" & ".join([tex_escape(r["measure"]), tex_escape(r["source"]), tex_escape(r["unit"])] + stat_cells(r) + [num(r["obs"], 0)]) + row_end)
    dep_lines.extend([r"\bottomrule", r"\end{tabular}"])

    indep_lines = [r"\begin{tabular}{lllrrrrrrr}", r"\toprule", "Measure & Source & Unit/stat & Mean & SD & P10 & P50 & P90 & Treated munis & Treated depts" + row_end, r"\midrule"]
    for _, r in indep.iterrows():
        treated_munis = "" if r.get("treated_munis", "") == "" else num(r["treated_munis"], 0)
        treated_depts = "" if r.get("treated_depts", "") == "" else num(r["treated_depts"], 0)
        indep_lines.append(" & ".join([tex_escape(r["measure"]), tex_escape(r["source"]), tex_escape(r["unit"])] + stat_cells(r) + [treated_munis, treated_depts]) + row_end)
    indep_lines.extend([r"\bottomrule", r"\end{tabular}"])

    tex = "\n".join([
        r"\begin{minipage}{\linewidth}",
        r"\centering",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\textbf{Panel A. Dependent nighttime-lights panel}\par\vspace{0.25em}",
        r"\resizebox{\linewidth}{!}{%",
        "\n".join(dep_lines),
        r"}",
        r"\vspace{0.8em}",
        r"\textbf{Panel B. Independent exposure measures}\par\vspace{0.25em}",
        r"\resizebox{\linewidth}{!}{%",
        "\n".join(indep_lines),
        r"}",
        r"\end{minipage}",
        "",
    ])
    for path in [PAPER / "appendix" / "summary_tables" / "table_exposure_summary_expanded.tex", OUT / "paper_figures" / "table_exposure_summary_expanded.tex"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tex, encoding="utf-8")


def legacy_exposure_summary(assignment: pd.DataFrame) -> pd.DataFrame:
    sample = assignment.loc[assignment["in_selected_country"].eq(1)].copy()
    rows = []
    for var, label, unit in [
        ("mp_x_gjst", "Mahajan-Parag x_gjst", "municipality/grid cell"),
        ("mp_pwind", "Mahajan-Parag predicted wind", "knots"),
        ("mp_grid_pop", "Mahajan-Parag grid population", "people"),
    ]:
        vals = sample[var]
        rows.append(
            {
                "panel": "Mahajan-Parag",
                "measure": label,
                "unit": unit,
                "native_continuous_variable": var.replace("mp_", ""),
                "mean": float(vals.mean()),
                "sd": float(vals.std(ddof=1)),
                "p50": float(vals.quantile(0.50)),
                "p90": float(vals.quantile(0.90)),
                "max": float(vals.max()),
                "nonzero_n": int(vals.gt(0).sum()),
                "binary_rule": "continuous exposure only",
                "treated": np.nan,
                "control": np.nan,
                "one_sd_means": (
                    f"{vals.std(ddof=1):.5f} index units"
                    if var == "mp_x_gjst"
                    else (f"{vals.std(ddof=1):.1f} knots" if var == "mp_pwind" else f"{vals.std(ddof=1):,.0f} people")
                ),
            }
        )
    return pd.DataFrame(rows)


def write_raw_mahajan_summary() -> None:
    df = pd.read_excel(ROOT / "raw" / "orlando_custom_mitch.xlsx")
    rows = []
    ca = df.loc[df["country"].isin(["Honduras", "El Salvador", "Guatemala", "Nicaragua", "Belize"])]
    for label, sub in [("All raw rows", df), ("Central America rows", ca)]:
        rows.append(
            {
                "sample": label,
                "rows": int(len(sub)),
                "countries": "; ".join(f"{k}: {v}" for k, v in sub["country"].value_counts().sort_index().items()),
                "mean_pwind": float(pd.to_numeric(sub["pwind"], errors="coerce").mean()),
                "mean_x_gjst": float(pd.to_numeric(sub["x_gjst"], errors="coerce").mean()),
                "sd_x_gjst": float(pd.to_numeric(sub["x_gjst"], errors="coerce").std(ddof=1)),
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "data" / "tables" / "assignment" / "mahajan_parag_raw_summary.csv", index=False)


def create_mahajan_appendix_panel() -> Path | None:
    src = next((path for path in MAHAJAN_APPENDIX_PDF_CANDIDATES if path.exists()), None)
    if src is None:
        return None
    page_prefix = WORKING / "mahajan_yang_appendix_page8"
    page_png = page_prefix.with_suffix(".png")
    try:
        subprocess.run(
            ["pdftoppm", "-f", "8", "-singlefile", "-png", "-r", "200", str(src), str(page_prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        if not page_png.exists():
            return None

    image = Image.open(page_png)
    crop = image.crop((150, 385, 2050, 1330))
    out_path = OUT / "paper_figures" / "mahajan_parag_appendix_grid_exposure.png"
    working_path = PAPER_LEGACY / "mahajan_parag_appendix_grid_exposure.png"
    working_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_path)
    crop.save(working_path)
    return out_path


def image_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) // 2
    y = box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), text, fill="black", font=font)


def fit_on_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    contained = ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    canvas.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
    return canvas


def render_threshold_map_panel(plot_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame, threshold: str, colors: dict[str, str]) -> Image.Image:
    bounds = plot_gdf.total_bounds
    xpad = (bounds[2] - bounds[0]) * 0.03
    ypad = (bounds[3] - bounds[1]) * 0.05
    classes = pd.Series("none", index=plot_gdf.index)
    if threshold in {"r34"}:
        classes.loc[plot_gdf[f"{EBTRK_TREAT_PREFIX}_r34_all"].eq(1)] = "34 kt"
    if threshold in {"r34", "r50"}:
        classes.loc[plot_gdf[f"{EBTRK_TREAT_PREFIX}_r50_all"].eq(1)] = "50 kt"
    classes.loc[plot_gdf[f"{EBTRK_TREAT_PREFIX}_r64_all"].eq(1)] = "64 kt"

    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    for lab in ["none", "34 kt", "50 kt", "64 kt"]:
        sub = plot_gdf.loc[classes.eq(lab)]
        if not sub.empty:
            sub.plot(ax=ax, color=colors[lab], edgecolor="#555555", linewidth=0.12)
    track = ebtrk.sort_values("iso_time").dropna(subset=["lon", "lat"])
    ax.plot(
        track["lon"],
        track["lat"],
        color="#111111",
        linewidth=1.6,
        solid_capstyle="round",
        path_effects=[pe.Stroke(linewidth=3.2, foreground="white"), pe.Normal()],
        zorder=8,
    )
    ax.scatter(
        track["lon"],
        track["lat"],
        s=8,
        color="#111111",
        edgecolor="white",
        linewidth=0.35,
        zorder=9,
    )
    ax.set_xlim(bounds[0] - xpad, bounds[2] + xpad)
    ax.set_ylim(bounds[1] - ypad, bounds[3] + ypad)
    ax.set_axis_off()
    tmp = WORKING / f"tmp_{threshold}_map_panel.png"
    fig.savefig(tmp, dpi=230, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return Image.open(tmp).convert("RGB")


def plot_ebtrk_maps(munis_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame) -> None:
    plot_gdf = munis_gdf.loc[munis_gdf["country_name"].isin(SELECTED_COUNTRIES)].copy().to_crs("EPSG:4326")
    appendix_panel = create_mahajan_appendix_panel()
    colors = {
        "none": "#f7f7f7",
        "34 kt": "#f4b6b6",
        "50 kt": "#df6a63",
        "64 kt": "#9f1d20",
    }
    map_panels = [render_threshold_map_panel(plot_gdf, ebtrk, threshold, colors) for threshold in THRESHOLDS]
    if appendix_panel is not None and appendix_panel.exists():
        mp_panel = Image.open(appendix_panel).convert("RGB")
    else:
        mp_panel = Image.new("RGB", (1600, 950), "white")
        draw_missing = ImageDraw.Draw(mp_panel)
        centered_text(draw_missing, (0, 0, 1600, 950), "Mahajan-Parag appendix image unavailable", image_font(34))

    cell_w, cell_h = 1300, 1120
    title_h, legend_h = 140, 170
    panel_title_h = 80
    content_size = (cell_w - 80, cell_h - panel_title_h - 40)
    canvas = Image.new("RGB", (2 * cell_w, title_h + 2 * cell_h + legend_h), "white")
    draw = ImageDraw.Draw(canvas)
    centered_text(draw, (0, 12, canvas.width, title_h - 18), "Extended Best Track threshold exposure", image_font(58, bold=False))

    panels = [
        ("64 kt winds and above", map_panels[0]),
        ("50 kt winds and above", map_panels[1]),
        ("34 kt winds and above", map_panels[2]),
        ("Continuous grid point exposure", mp_panel),
    ]
    for idx, (title, panel) in enumerate(panels):
        x0 = (idx % 2) * cell_w
        y0 = title_h + (idx // 2) * cell_h
        centered_text(draw, (x0, y0, x0 + cell_w, y0 + panel_title_h), title, image_font(36))
        fitted = fit_on_canvas(panel, content_size)
        canvas.paste(fitted, (x0 + 40, y0 + panel_title_h + 10))

    legend_y = title_h + 2 * cell_h + 35
    centered_text(draw, (0, legend_y - 10, canvas.width, legend_y + 35), "Highest EBTRK threshold meeting the 50 percent municipal-area rule", image_font(28))
    start_x = canvas.width // 2 - 310
    for i, lab in enumerate(["34 kt", "50 kt", "64 kt"]):
        x = start_x + i * 230
        draw.rectangle((x, legend_y + 55, x + 34, legend_y + 89), fill=colors[lab], outline="#555555", width=3)
        draw.text((x + 48, legend_y + 50), lab, fill="black", font=image_font(30))
    line_x = start_x + 3 * 230
    draw.line((line_x, legend_y + 72, line_x + 52, legend_y + 72), fill="black", width=6)
    draw.text((line_x + 66, legend_y + 50), "Mitch track", fill="black", font=image_font(30))

    for path in [
        OUT / "data" / "figures" / "map_ebtrk_thresholds.png",
        OUT / "paper_figures" / "map_ebtrk_thresholds.png",
        PAPER_LEGACY / "map_ebtrk_thresholds.png",
    ]:
        canvas.save(path)


def render_binary_map_panel(plot_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame, flag_col: str, fill: str) -> Image.Image:
    bounds = plot_gdf.total_bounds
    xpad = (bounds[2] - bounds[0]) * 0.03
    ypad = (bounds[3] - bounds[1]) * 0.05
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    plot_gdf.plot(ax=ax, color="#f7f7f7", edgecolor="#555555", linewidth=0.12)
    sub = plot_gdf.loc[plot_gdf[flag_col].eq(1)]
    if not sub.empty:
        sub.plot(ax=ax, color=fill, edgecolor="#333333", linewidth=0.18)
    track = ebtrk.sort_values("iso_time").dropna(subset=["lon", "lat"])
    ax.plot(track["lon"], track["lat"], color="#111111", linewidth=1.6, path_effects=[pe.Stroke(linewidth=3.2, foreground="white"), pe.Normal()], zorder=8)
    ax.set_xlim(bounds[0] - xpad, bounds[2] + xpad)
    ax.set_ylim(bounds[1] - ypad, bounds[3] + ypad)
    ax.set_axis_off()
    tmp = WORKING / f"tmp_{flag_col}_map_panel.png"
    fig.savefig(tmp, dpi=230, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return Image.open(tmp).convert("RGB")



def plot_expanded_maps(munis_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame) -> None:
    plot_gdf = munis_gdf.loc[munis_gdf["country_name"].isin(SELECTED_COUNTRIES)].copy().to_crs("EPSG:4326")
    if "pre_mean_stable_sum" not in plot_gdf.columns:
        attrs_path = WORKING / "data" / "processed" / "municipality_attributes.csv"
        if attrs_path.exists():
            attrs = pd.read_csv(attrs_path, usecols=["muni_key", "pre_mean_stable_sum"])
            plot_gdf = plot_gdf.merge(attrs, on="muni_key", how="left")
    if "state_key" not in plot_gdf.columns:
        plot_gdf["state_key"] = plot_gdf["country_name"].astype(str) + "|" + plot_gdf["department_name"].astype(str)
    plot_gdf = add_state_impacts(plot_gdf)
    plot_gdf = add_expanded_exposure_flags(plot_gdf)
    colors = {"none": "#f7f7f7", "34 kt": "#f4b6b6", "50 kt": "#df6a63", "64 kt": "#9f1d20"}
    panels = [
        ("64 kt winds and above", render_threshold_map_panel(plot_gdf, ebtrk, "r64", colors)),
        ("50 kt winds and above", render_threshold_map_panel(plot_gdf, ebtrk, "r50", colors)),
        ("CHIRPS max-rainfall anomaly top decile", render_binary_map_panel(plot_gdf, ebtrk, "chirps_max_anomaly_top10", "#7f1d1d")),
        ("Deaths per capita top decile (state-level)", render_binary_map_panel(plot_gdf, ebtrk, "death_pc_top10_state", "#525252")),
    ]
    cell_w, cell_h, title_h, legend_h, panel_title_h = 1300, 1120, 140, 120, 90
    canvas = Image.new("RGB", (2 * cell_w, title_h + 2 * cell_h + legend_h), "white")
    draw = ImageDraw.Draw(canvas)
    centered_text(draw, (0, 12, canvas.width, title_h - 18), "Expanded exposure maps", image_font(58))
    content_size = (cell_w - 80, cell_h - panel_title_h - 40)
    for idx, (title, panel) in enumerate(panels):
        x0 = (idx % 2) * cell_w
        y0 = title_h + (idx // 2) * cell_h
        centered_text(draw, (x0 + 20, y0, x0 + cell_w - 20, y0 + panel_title_h), title, image_font(31))
        canvas.paste(fit_on_canvas(panel, content_size), (x0 + 40, y0 + panel_title_h + 10))
    centered_text(draw, (0, title_h + 2 * cell_h + 20, canvas.width, title_h + 2 * cell_h + 80), "Bottom panels add standalone CHIRPS rainfall and state-level deaths per capita treatments.", image_font(25))
    for base in [EXPANDED_OUT, EXPANDED_OVERLEAF]:
        base.mkdir(parents=True, exist_ok=True)
        canvas.save(base / "map_exposure_maps_expanded.png")

@dataclass
class RegressionResult:
    measure: str
    sample: str
    year_fe: bool
    coef: float
    se: float
    p: float
    n: int
    r2: float
    treated_units: float
    control_units: float


def residualize(values: np.ndarray, units: np.ndarray, years: np.ndarray | None = None) -> np.ndarray:
    df = pd.DataFrame({"v": values, "u": units})
    out = values - df.groupby("u")["v"].transform("mean").to_numpy()
    if years is not None:
        df2 = pd.DataFrame({"v": values, "u": units, "t": years})
        out = values - df2.groupby("u")["v"].transform("mean").to_numpy() - df2.groupby("t")["v"].transform("mean").to_numpy() + float(np.mean(values))
    return out


def cluster_ols(y: np.ndarray, x: np.ndarray, clusters: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    mask = np.isfinite(y) & np.isfinite(x).all(axis=1)
    y = y[mask]
    x = x[mask, :]
    clusters = clusters[mask]
    xtx = x.T @ x
    inv = np.linalg.pinv(xtx)
    beta = inv @ (x.T @ y)
    resid = y - x @ beta
    meat = np.zeros((x.shape[1], x.shape[1]))
    for g in np.unique(clusters):
        idx = clusters == g
        xg = x[idx, :]
        ug = resid[idx][:, None]
        meat += xg.T @ ug @ ug.T @ xg
    g = len(np.unique(clusters))
    n = len(y)
    k = x.shape[1]
    corr = (g / max(g - 1, 1)) * ((n - 1) / max(n - k, 1))
    vcov = corr * inv @ meat @ inv
    se = np.sqrt(np.maximum(np.diag(vcov), 0))
    ssr = float(np.sum(resid**2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ssr / sst if sst > 0 else np.nan
    return beta, se, r2


def pvalue_from_t(t: float) -> float:
    try:
        import scipy.stats as st

        return float(2 * st.t.sf(abs(t), 999999))
    except Exception:
        return float(math.erfc(abs(t) / math.sqrt(2)))


def run_did(panel: pd.DataFrame, treat_col: str, measure: str, sample_label: str, year_fe: bool, continuous: bool = False) -> RegressionResult:
    df = panel.dropna(subset=["log_ntl", treat_col, "year", "muni_unit_id"]).copy()
    base = df.drop_duplicates("muni_unit_id")
    if not continuous and (base[treat_col].eq(1).sum() == 0 or base[treat_col].eq(0).sum() == 0):
        return RegressionResult(
            measure,
            sample_label,
            year_fe,
            np.nan,
            np.nan,
            np.nan,
            int(len(df)),
            np.nan,
            float(base[treat_col].eq(1).sum()),
            float(base[treat_col].eq(0).sum()),
        )
    df["post"] = (df["year"] >= 1998).astype(float)
    df["treat_post"] = df[treat_col].astype(float) * df["post"]
    xcols = ["treat_post"] if year_fe else ["post", "treat_post"]
    y = residualize(df["log_ntl"].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None)
    x = np.column_stack([residualize(df[c].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None) for c in xcols])
    beta, se, r2 = cluster_ols(y, x, df["muni_unit_id"].to_numpy())
    idx = xcols.index("treat_post")
    t = beta[idx] / se[idx] if se[idx] > 0 else np.nan
    if continuous:
        treated_units = float(base[treat_col].std(ddof=1))
        control_units = float(base[treat_col].mean())
    else:
        treated_units = float(base[treat_col].eq(1).sum())
        control_units = float(base[treat_col].eq(0).sum())
    return RegressionResult(measure, sample_label, year_fe, float(beta[idx]), float(se[idx]), pvalue_from_t(t), int(len(df)), float(r2), treated_units, control_units)


def build_panel(assignment: pd.DataFrame) -> pd.DataFrame:
    panel = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    panel["stable_sum"] = pd.to_numeric(panel["stable_sum"], errors="coerce")
    panel["log_ntl"] = np.log1p(panel["stable_sum"])
    panel = panel.drop(columns=[c for c in ["pre_mean_stable_sum"] if c in panel.columns])
    keep_cols = ["muni_key", "in_selected_country", "pre_mean_stable_sum", "mp_x_gjst_z_nofilter", "mp_x_gjst_z_prefilter", "mp_x_gjst", "chirps_max_anomaly_top10", "death_pc_top10_state", "rain50_chirps_top10", "ebtrk_share_r64_all", "ebtrk_share_r50_all", "ebtrk_share_r34_all"]
    for threshold in THRESHOLDS:
        for bundle, _ in BUNDLES:
            keep_cols.append(f"{EBTRK_TREAT_PREFIX}_{threshold}_{bundle.lower()}")
    df = panel.merge(assignment[keep_cols], on="muni_key", how="inner")
    df = df.loc[df["in_selected_country"].eq(1)].copy()
    df["muni_unit_id"] = pd.factorize(df["muni_key"])[0] + 1
    return df


def build_death_state_panel(assignment: pd.DataFrame) -> pd.DataFrame:
    ntl = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    ntl["stable_sum"] = pd.to_numeric(ntl["stable_sum"], errors="coerce")
    keep = ["muni_key", "state_key", "country_name", "department_name", "in_selected_country", "has_death_data", "death_pc_top10_state", "death_pc_top10_state_cutoff", "deaths_per_capita"]
    merged = ntl.merge(assignment[keep], on="muni_key", how="inner")
    merged = merged.loc[merged["in_selected_country"].eq(1) & merged["has_death_data"].eq(1)].copy()
    state = merged.groupby(["state_key", "year"], as_index=False).agg(
        stable_sum=("stable_sum", "sum"),
        country_name=("country_name", "first"),
        department_name=("department_name", "first"),
        deaths_per_capita=("deaths_per_capita", "first"),
        death_pc_top10_state=("death_pc_top10_state", "first"),
        death_pc_top10_state_cutoff=("death_pc_top10_state_cutoff", "first"),
    )
    state["log_ntl"] = np.log1p(pd.to_numeric(state["stable_sum"], errors="coerce").clip(lower=0))
    pre_mean = state.loc[state["year"].le(1997)].groupby("state_key")["stable_sum"].mean()
    state["pre_mean_stable_sum"] = state["state_key"].map(pre_mean)
    state["muni_key"] = state["state_key"]
    state["muni_unit_id"] = pd.factorize(state["state_key"])[0] + 1
    state["in_selected_country"] = 1
    return state


def load_death_state_panel() -> pd.DataFrame:
    global DEATH_STATE_PANEL_CACHE
    if DEATH_STATE_PANEL_CACHE is None:
        path = WORKING / "data" / "processed" / "state_year_panel_deaths.csv"
        if path.exists():
            DEATH_STATE_PANEL_CACHE = pd.read_csv(path)
        else:
            assignment = pd.read_csv(OUT / "data" / "tables" / "assignment" / "assignment_municipalities.csv")
            DEATH_STATE_PANEL_CACHE = build_death_state_panel(assignment)
            path.parent.mkdir(parents=True, exist_ok=True)
            DEATH_STATE_PANEL_CACHE.to_csv(path, index=False)
    return DEATH_STATE_PANEL_CACHE.copy()


def panel_for_spec(panel: pd.DataFrame, spec: dict) -> pd.DataFrame:
    if spec.get("panel") == "state":
        return load_death_state_panel()
    return panel


def star(p: float) -> str:
    if pd.isna(p):
        return ""
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.10:
        return "*"
    return ""


def regression_tex(rows: list[RegressionResult], continuous: bool = False) -> str:
    lines = [
        r"\begin{tabular}{llrrrrr}",
        r"\toprule",
        r"Measure & Sample & Year FE & Coef. & SE & N & Treated/scale \\",
        r"\midrule",
    ]
    for r in rows:
        scale = fmt(r.treated_units, 3) if continuous else fmt(r.treated_units, 0)
        coef = "--" if pd.isna(r.coef) else f"{r.coef:.3f}{star(r.p)}"
        se = "" if pd.isna(r.se) else f"({r.se:.3f})"
        lines.append(
            " & ".join(
                [
                    tex_escape(r.measure),
                    tex_escape(r.sample),
                    "Yes" if r.year_fe else "No",
                    coef,
                    se,
                    fmt(r.n, 0),
                    scale,
                ]
            )
            + r" \\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def event_coefficients(panel: pd.DataFrame, treat_col: str, prefilter: bool, year_fe: bool) -> pd.DataFrame:
    df = panel.loc[panel["pre_mean_stable_sum"].notna()].copy()
    if prefilter:
        df = df.loc[df["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
    base = df.drop_duplicates("muni_unit_id")
    if base[treat_col].eq(1).sum() == 0 or base[treat_col].eq(0).sum() == 0:
        return pd.DataFrame(
            [{"year": y, "coef": np.nan, "se": np.nan, "p": np.nan, "reference": int(y == 1997)} for y in EVENT_TABLE_YEARS]
        )
    xcols = []
    years = sorted(df["year"].unique())
    for y in years:
        if y == 1997:
            continue
        col = f"event_{y}"
        df[col] = df[treat_col].astype(float) * df["year"].eq(y).astype(float)
        xcols.append(col)
    yres = residualize(df["log_ntl"].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None)
    xres = np.column_stack(
        [residualize(df[c].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None) for c in xcols]
    )
    beta, se, _ = cluster_ols(yres, xres, df["muni_unit_id"].to_numpy())
    rows = [{"year": 1997, "coef": 0.0, "se": np.nan, "p": np.nan, "reference": 1}]
    for col, b, s in zip(xcols, beta, se):
        t = b / s if s > 0 else np.nan
        rows.append({"year": int(col.replace("event_", "")), "coef": float(b), "se": float(s), "p": pvalue_from_t(t), "reference": 0})
    out = pd.DataFrame(rows)
    return out.loc[out["year"].isin(EVENT_TABLE_YEARS)].sort_values("year").reset_index(drop=True)


def event_table_cell(coef: float, se: float, p: float, year: int, reference: bool = False) -> str:
    if reference:
        return "ref."
    if pd.isna(coef):
        return "--"
    txt = f"{coef:.3f}{star(p)}"
    if pd.notna(se):
        txt = rf"\begin{{tabular}}{{@{{}}c@{{}}}}{txt}\\{{\scriptsize ({se:.3f})}}\end{{tabular}}"
    if year >= 1999 and coef < 0:
        return rf"\cellcolor{{gray!18}}{txt}"
    return txt


def period_label(start: int, end: int) -> str:
    return f"{str(start)[-2:]}'-{str(end)[-2:]}'"


def period_midpoint(start: int, end: int) -> float:
    return (start + end) / 2


def filter_panel_by_pre_ntl_snr(panel: pd.DataFrame, threshold: float = 1.0) -> pd.DataFrame:
    pre = (
        panel.loc[panel["year"].le(1997)]
        .groupby("muni_unit_id")["stable_sum"]
        .agg(pre_mean="mean", pre_sd="std")
    )
    snr = pre["pre_mean"].div(pre["pre_sd"])
    keep = pre["pre_mean"].gt(0) & (pre["pre_sd"].eq(0) | snr.ge(threshold))
    return panel.loc[panel["muni_unit_id"].isin(pre.index[keep])].copy()


def event_period_coefficients(
    panel: pd.DataFrame,
    treat_col: str,
    prefilter: bool,
    year_fe: bool,
    binary: bool = True,
) -> pd.DataFrame:
    df = panel.loc[panel["pre_mean_stable_sum"].notna()].copy()
    if prefilter:
        df = df.loc[df["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
    base = df.drop_duplicates("muni_unit_id")
    if binary and (base[treat_col].eq(1).sum() == 0 or base[treat_col].eq(0).sum() == 0):
        return pd.DataFrame(
            [
                {
                    "period_start": start,
                    "period_end": end,
                    "period": period_label(start, end),
                    "x": period_midpoint(start, end),
                    "coef": np.nan,
                    "se": np.nan,
                    "p": np.nan,
                    "lb": np.nan,
                    "ub": np.nan,
                    "reference": int((start, end) == REFERENCE_PERIOD),
                }
                for start, end in EVENT_PERIODS
            ]
        )

    xcols = []
    for start, end in EVENT_PERIODS:
        if (start, end) == REFERENCE_PERIOD:
            continue
        col = f"event_{start}_{end}"
        df[col] = df[treat_col].astype(float) * df["year"].between(start, end).astype(float)
        xcols.append(col)
    yres = residualize(df["log_ntl"].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None)
    xres = np.column_stack(
        [residualize(df[c].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None) for c in xcols]
    )
    beta, se, _ = cluster_ols(yres, xres, df["muni_unit_id"].to_numpy())
    results = {
        REFERENCE_PERIOD: {
            "coef": 0.0,
            "se": np.nan,
            "p": np.nan,
            "lb": np.nan,
            "ub": np.nan,
            "reference": 1,
        }
    }
    for col, b, s in zip(xcols, beta, se):
        _, start, end = col.split("_")
        key = (int(start), int(end))
        t = b / s if s > 0 else np.nan
        results[key] = {
            "coef": float(b),
            "se": float(s),
            "p": pvalue_from_t(t),
            "lb": float(b - 1.96 * s),
            "ub": float(b + 1.96 * s),
            "reference": 0,
        }

    rows = []
    for start, end in EVENT_PERIODS:
        vals = results[(start, end)]
        rows.append(
            {
                "period_start": start,
                "period_end": end,
                "period": period_label(start, end),
                "x": period_midpoint(start, end),
                **vals,
            }
        )
    return pd.DataFrame(rows)


def shade_for_significance(p: float) -> str:
    if pd.isna(p):
        return "gray!13"
    if p < 0.01:
        return "gray!39"
    if p < 0.05:
        return "gray!30"
    if p < 0.10:
        return "gray!21"
    return "gray!11"


def period_event_table_cell(coef: float, se: float, p: float, start: int, reference: bool = False) -> str:
    if reference:
        return "ref."
    if pd.isna(coef):
        return "--"
    txt = f"{coef:.3f}{star(p)}"
    if pd.notna(se):
        txt = "\\begin{tabular}{@{}c@{}}" + txt + "\\\\{\\scriptsize (" + f"{se:.3f}" + ")}\\end{tabular}"
    if start >= 1998 and coef < 0:
        return rf"\cellcolor{{{shade_for_significance(p)}}}{txt}"
    return txt


def table_period_label(start: int, end: int) -> str:
    label = period_label(start, end)
    if (start, end) == (2008, 2009):
        return label + r"$\ldots$"
    return label


def spec_label_tex(label: str) -> str:
    if label == "Unit + Year FE for pre-Mitch NTL median":
        return "\\begin{tabular}{@{}l@{}}Unit + Year FE\\\\for pre-Mitch NTL median\\end{tabular}"
    return tex_escape(label)

def write_ebtrk_event_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    display_headers = [r"$\cdots$"] + [period_label(start, end) for start, end in TABLE_EVENT_PERIODS] + [r"$\cdots$"]
    tex_lines = [
        rf"\begin{{tabular}}{{lccc{'r' * len(display_headers)}}}",
        r"\toprule",
        r"Measure & $\alpha_i$ & $\lambda_t$ & Ref. & " + " & ".join(display_headers) + r" \\",
        r"\midrule",
    ]
    for threshold in THRESHOLDS:
        treat_col = f"{EBTRK_TREAT_PREFIX}_{threshold}_all"
        specs = [
            (f"{THRESHOLD_LABELS[threshold]} winds and above", False, False),
            (r"\hspace{1em}with year FE", False, True),
            (r"\hspace{1em}with pre-Mitch NTL median and year FE", True, True),
        ]
        for label, prefilter, year_fe in specs:
            ev = event_period_coefficients(panel, treat_col, prefilter=prefilter, year_fe=year_fe, binary=True)
            record = {"threshold": threshold, "row_label": label, "prefilter": prefilter, "year_fe": year_fe}
            for start, end in EVENT_PERIODS:
                current = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
                record[f"coef_{start}_{end}"] = current["coef"]
                record[f"se_{start}_{end}"] = current["se"]
                record[f"p_{start}_{end}"] = current["p"]
            cells = []
            for start, end in TABLE_EVENT_PERIODS:
                current = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
                cells.append(period_event_table_cell(current["coef"], current["se"], current["p"], start, bool(current["reference"])))
            rows.append(record)
            fe_cells = ["Yes", "Yes" if year_fe else "No", period_label(*REFERENCE_PERIOD)]
            tex_lines.append(label + " & " + " & ".join(fe_cells + [r"$\cdots$"] + cells + [r"$\cdots$"]) + r" \\")
        if threshold != THRESHOLDS[-1]:
            tex_lines.append(r"\addlinespace")
    tex_lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    out = pd.DataFrame(rows)
    for path in [
        OUT / "results" / "tables" / "event_study_table_ebtrk_thresholds.csv",
        OUT / "results" / "tables" / "event_study_table_ebtrk_thresholds_twoyear.csv",
    ]:
        out.to_csv(path, index=False)
    tex = "\n".join(tex_lines)
    write_text_outputs([
        OUT / "paper_figures" / "regression_table_ebtrk_binary.tex",
        PAPER_ROOT / "regression_table_ebtrk_binary.tex",
        PAPER_LEGACY / "regression_table_ebtrk_binary.tex",
    ], tex)
    return out


def write_recovery_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        col = f"{EBTRK_TREAT_PREFIX}_{threshold}_all"
        gap = visual_gap(panel, col, prefilter=False)
        post = gap.loc[gap.index >= 1998]
        initial_negative = 0
        for value in post:
            if value < 0:
                initial_negative += 1
            else:
                break
        ev = event_coefficients(panel, col, prefilter=False, year_fe=True).set_index("year")
        rows.append(
            {
                "threshold": threshold,
                "treated_units": int(panel.drop_duplicates("muni_key")[col].sum()),
                "coef_1998_year_fe": float(ev.loc[1998, "coef"]),
                "coef_1999_year_fe": float(ev.loc[1999, "coef"]),
                "pct_1998_year_fe": float(np.exp(ev.loc[1998, "coef"]) - 1),
                "pct_1999_year_fe": float(np.exp(ev.loc[1999, "coef"]) - 1),
                "initial_years_below_counterfactual": initial_negative,
                "first_nonnegative_gap_year": int(post.loc[post.ge(0)].index.min()) if post.ge(0).any() else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "results" / "tables" / "ebtrk_recovery_interpretation.csv", index=False)
    return out


def write_mp_annual_table(panel: pd.DataFrame, assignment: pd.DataFrame) -> pd.DataFrame:
    sample = assignment.loc[assignment["in_selected_country"].eq(1)].copy()
    mean = float(sample["mp_x_gjst"].mean())
    sd = float(sample["mp_x_gjst"].std(ddof=1))
    positive = sample.loc[sample["mp_x_gjst"].gt(0), "mp_x_gjst"]
    p90_positive = float(positive.quantile(0.90)) if len(positive) else np.nan
    z90_positive = (p90_positive - mean) / sd if sd > 0 and np.isfinite(p90_positive) else np.nan

    rows = []
    specs = [
        ("Point Exposure Index (SD)", "mp_x_gjst_z_nofilter", False, False, 1.0),
        (r"\hspace{1em}with year FE", "mp_x_gjst_z_nofilter", False, True, 1.0),
        (r"\hspace{1em}with pre-Mitch NTL median and year FE", "mp_x_gjst_z_prefilter", True, True, 1.0),
        ("90th percentile positive index, implied", "mp_x_gjst_z_nofilter", False, True, z90_positive),
    ]
    display_headers = [r"$\cdots$"] + [period_label(start, end) for start, end in TABLE_EVENT_PERIODS] + [r"$\cdots$"]
    tex_lines = [
        rf"\begin{{tabular}}{{lccc{'r' * len(display_headers)}}}",
        r"\toprule",
        r"Measure & $\alpha_i$ & $\lambda_t$ & Ref. & " + " & ".join(display_headers) + r" \\",
        r"\midrule",
    ]
    for label, col, prefilter, year_fe, multiplier in specs:
        ev = event_period_coefficients(panel, col, prefilter=prefilter, year_fe=year_fe, binary=False)
        record = {
            "row_label": label,
            "prefilter": prefilter,
            "year_fe": year_fe,
            "multiplier": multiplier,
            "p90_positive_x_gjst": p90_positive,
            "p90_positive_z": z90_positive,
        }
        for start, end in EVENT_PERIODS:
            current = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
            coef = float(current["coef"]) * multiplier if pd.notna(multiplier) else np.nan
            se = float(current["se"]) * abs(multiplier) if pd.notna(current["se"]) and pd.notna(multiplier) else np.nan
            record[f"coef_{start}_{end}"] = coef
            record[f"se_{start}_{end}"] = se
            record[f"p_{start}_{end}"] = current["p"]
        cells = []
        for start, end in TABLE_EVENT_PERIODS:
            current = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
            reference = bool(current["reference"])
            coef = float(current["coef"]) * multiplier if pd.notna(multiplier) else np.nan
            se = float(current["se"]) * abs(multiplier) if pd.notna(current["se"]) and pd.notna(multiplier) else np.nan
            cells.append(period_event_table_cell(coef, se, current["p"], start, reference))
        rows.append(record)
        fe_cells = ["Yes", "Yes" if year_fe else "No", period_label(*REFERENCE_PERIOD)]
        tex_lines.append(label + " & " + " & ".join(fe_cells + [r"$\cdots$"] + cells + [r"$\cdots$"]) + r" \\")
    tex_lines.extend([r"\bottomrule", r"\end{tabular}", ""])

    out = pd.DataFrame(rows)
    for path in [
        OUT / "results" / "tables" / "regression_table_mahajan_continuous.csv",
        OUT / "results" / "tables" / "regression_table_mahajan_continuous_twoyear.csv",
    ]:
        out.to_csv(path, index=False)
    post = out.loc[out["row_label"].eq("90th percentile positive index, implied")].iloc[0]
    post_periods = [(start, end) for start, end in EVENT_PERIODS if start >= 1998 and pd.notna(post[f"coef_{start}_{end}"])]
    initial_negative = 0
    for start, end in post_periods:
        if post[f"coef_{start}_{end}"] < 0:
            initial_negative += 1
        else:
            break
    first_nonnegative = next(
        (period_label(start, end) for start, end in post_periods if post[f"coef_{start}_{end}"] >= 0),
        "",
    )
    pd.DataFrame(
        [
            {
                "p90_positive_x_gjst": p90_positive,
                "p90_positive_z": z90_positive,
                "initial_negative_periods_1998_onward": initial_negative,
                "first_nonnegative_period_1998_onward": first_nonnegative,
            }
        ]
    ).to_csv(OUT / "results" / "tables" / "mahajan_continuous_recovery_interpretation.csv", index=False)

    tex = "\n".join(tex_lines)
    write_text_outputs([
        OUT / "paper_figures" / "regression_table_mahajan_continuous.tex",
        PAPER_ROOT / "regression_table_mahajan_continuous.tex",
        PAPER_LEGACY / "regression_table_mahajan_continuous.tex",
    ], tex)
    return out


def run_regressions(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    binary_df = write_ebtrk_event_table(panel)
    write_recovery_summary(panel)
    assignment = pd.read_csv(OUT / "data" / "tables" / "assignment" / "assignment_municipalities.csv")
    cont_df = write_mp_annual_table(panel, assignment)
    return binary_df, cont_df


def did_series(panel: pd.DataFrame, treat_col: str, prefilter: bool = False, year_fe: bool = False) -> pd.DataFrame:
    df = panel.loc[panel["pre_mean_stable_sum"].notna()].copy()
    if prefilter:
        df = df.loc[df["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
    if year_fe:
        df["adj"] = residualize(df["log_ntl"].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy())
    else:
        unit_mean = df.groupby("muni_unit_id")["log_ntl"].transform("mean")
        df["adj"] = df["log_ntl"] - unit_mean + df["log_ntl"].mean()
    df["treated"] = df[treat_col].astype(float)
    out = df.groupby(["year", "treated"], as_index=False)["adj"].mean()
    return out


def visual_gap(panel: pd.DataFrame, treat_col: str, prefilter: bool = False) -> pd.Series:
    series = did_series(panel, treat_col, prefilter=prefilter)
    wide = series.pivot(index="year", columns="treated", values="adj")
    if 0.0 not in wide.columns or 1.0 not in wide.columns or 1997 not in wide.index:
        return pd.Series(dtype=float)
    treated_base = wide.loc[1997, 1.0]
    control_base = wide.loc[1997, 0.0]
    counterfactual = treated_base + (wide[0.0] - control_base)
    return wide[1.0] - counterfactual


def event_series(panel: pd.DataFrame, treat_col: str, continuous: bool = False, prefilter: bool = False, year_fe: bool = True) -> pd.DataFrame:
    df = panel.loc[panel["pre_mean_stable_sum"].notna()].copy()
    if prefilter:
        df = df.loc[df["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
    years = sorted(df["year"].unique())
    xcols = []
    for y in years:
        if y == 1997:
            continue
        col = f"event_{y}"
        df[col] = df[treat_col].astype(float) * (df["year"].eq(y).astype(float))
        xcols.append(col)
    yres = residualize(df["log_ntl"].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None)
    xres = np.column_stack(
        [residualize(df[c].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy() if year_fe else None) for c in xcols]
    )
    beta, se, _ = cluster_ols(yres, xres, df["muni_unit_id"].to_numpy())
    rows = [{"year": 1997, "coef": 0.0, "se": np.nan, "lb": np.nan, "ub": np.nan, "reference": 1}]
    for col, b, s in zip(xcols, beta, se):
        year = int(col.replace("event_", ""))
        rows.append({"year": year, "coef": b, "se": s, "lb": b - 1.96 * s, "ub": b + 1.96 * s, "reference": 0})
    return pd.DataFrame(rows).sort_values("year")


def did_period_series(panel: pd.DataFrame, treat_col: str, prefilter: bool = False, year_fe: bool = False) -> pd.DataFrame:
    df = panel.loc[panel["pre_mean_stable_sum"].notna()].copy()
    if prefilter:
        df = df.loc[df["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
    df["period_start"] = 1992 + 2 * np.floor((df["year"] - 1992) / 2).astype(int)
    if year_fe:
        df["adj"] = residualize(df["log_ntl"].to_numpy(float), df["muni_unit_id"].to_numpy(), df["year"].to_numpy())
    else:
        unit_mean = df.groupby("muni_unit_id")["log_ntl"].transform("mean")
        df["adj"] = df["log_ntl"] - unit_mean + df["log_ntl"].mean()
    df["treated"] = df[treat_col].astype(float)
    out = df.groupby(["period_start", "treated"], as_index=False)["adj"].mean()
    out["period"] = out["period_start"].map(lambda y: period_label(int(y), int(y) + 1))
    return out


def write_reghdfe_bridge(panel: pd.DataFrame) -> None:
    bridge_dir = WORKING / "data" / "processed" / "reghdfe"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    reg_panel = pd.DataFrame(
        {
            "muni_unit_id": panel["muni_unit_id"],
            "year": panel["year"],
            "log_ntl": panel["log_ntl"],
            "pre_mean_stable_sum": panel["pre_mean_stable_sum"],
            "t_r64": panel[f"{EBTRK_TREAT_PREFIX}_r64_all"],
            "t_r50": panel[f"{EBTRK_TREAT_PREFIX}_r50_all"],
            "t_r34": panel[f"{EBTRK_TREAT_PREFIX}_r34_all"],
            "t_chirps": panel["chirps_max_anomaly_top10"],
            "t_death": panel["death_pc_top10_state"],
            "c_r50": panel["ebtrk_share_r50_all"],
            "c_mpz": panel["mp_x_gjst_z_nofilter"],
        }
    )
    reg_panel.to_csv(bridge_dir / "event_panel_for_reghdfe.csv", index=False)
    do_path = WORKING / "scripts" / "legacy" / "19_reghdfe_event_tables.do"
    pairs = " ".join(f"{start}_{end}" for start, end in EVENT_PERIODS)
    do_text = f'''version 18
clear all
set more off
cd "Z:/home/orlando-valladares/Trabajo/ECON64"
capture log close reghdfe_event
capture mkdir "working/logs"
log using "working/logs/reghdfe_event_tables.log", replace name(reghdfe_event) text
adopath ++ "working/ado"
adopath ++ "working/ado/require_src/src"
adopath ++ "working/ado/ftools_src/src"
adopath ++ "working/ado/reghdfe_src/current-code"
adopath ++ "working/ado/reghdfe_src/src"
capture which reghdfe
if _rc {{
    display as error "reghdfe not found. Place reghdfe/ftools ado files in working/ado or install them in the Stata bottle."
    exit 111
}}
import delimited using "working/data/processed/reghdfe/event_panel_for_reghdfe.csv", clear varnames(1)

capture program drop run_event
program define run_event
    syntax, Rowlabel(string) Treatvar(name) Prefilter(integer) Yearfe(integer)
    preserve
    display as text "=== `rowlabel' ==="
    if `prefilter' == 1 {{
        keep if pre_mean_stable_sum >= {PRE_MITCH_NTL_MEDIAN:.2f} & !missing(pre_mean_stable_sum)
    }}
    local rhs ""
    foreach pair in {pairs} {{
        local us = strpos("`pair'", "_")
        local start = real(substr("`pair'", 1, `us' - 1))
        local end = real(substr("`pair'", `us' + 1, .))
        if !( `start' == 1996 & `end' == 1997 ) {{
            local v ev_`start'_`end'
            capture drop `v'
            gen double `v' = `treatvar' * inrange(year, `start', `end')
            local rhs `rhs' `v'
        }}
    }}
    if `yearfe' == 1 {{
        reghdfe log_ntl `rhs', absorb(muni_unit_id year) vce(cluster muni_unit_id)
    }}
    else {{
        reghdfe log_ntl `rhs', absorb(muni_unit_id) vce(cluster muni_unit_id)
    }}
    restore
end

run_event, rowlabel("64 kt winds and above") treatvar(t_r64) prefilter(0) yearfe(0)
run_event, rowlabel("64 kt with year FE") treatvar(t_r64) prefilter(0) yearfe(1)
run_event, rowlabel("64 kt pre-Mitch NTL median and year FE") treatvar(t_r64) prefilter(1) yearfe(1)
run_event, rowlabel("50 kt winds and above") treatvar(t_r50) prefilter(0) yearfe(0)
run_event, rowlabel("50 kt with year FE") treatvar(t_r50) prefilter(0) yearfe(1)
run_event, rowlabel("50 kt pre-Mitch NTL median and year FE") treatvar(t_r50) prefilter(1) yearfe(1)
run_event, rowlabel("34 kt winds and above") treatvar(t_r34) prefilter(0) yearfe(0)
run_event, rowlabel("34 kt with year FE") treatvar(t_r34) prefilter(0) yearfe(1)
run_event, rowlabel("34 kt pre-Mitch NTL median and year FE") treatvar(t_r34) prefilter(1) yearfe(1)
run_event, rowlabel("Mahajan-Parag point exposure index SD") treatvar(c_mpz) prefilter(0) yearfe(1)
run_event, rowlabel("CHIRPS max-rainfall anomaly top decile") treatvar(t_chirps) prefilter(0) yearfe(1)
run_event, rowlabel("Deaths per capita top decile state-level") treatvar(t_death) prefilter(0) yearfe(1)
run_event, rowlabel("50 kt municipal coverage share") treatvar(c_r50) prefilter(0) yearfe(1)
log close reghdfe_event
'''
    do_path.write_text(do_text, encoding="utf-8")
    status_path = bridge_dir / "reghdfe_status.txt"
    native = next((shutil.which(name) for name in ["stata-mp", "stata-se", "stata"] if shutil.which(name)), None)
    if native is not None:
        cmd = [native, "-b", "do", str(do_path)]
    elif shutil.which("flatpak"):
        cmd = ["flatpak", "run", f"--filesystem={ROOT}", "--command=bottles-cli", "com.usebottles.bottles", "run", "-b", "Stata", "-p", "StataSE-64", "--args-replace", "/e", "do", f"Z:{do_path.as_posix()}"]
    else:
        status_path.write_text("No native Stata or Flatpak/Bottles Stata executable available; reghdfe bridge files were written but not run.\n", encoding="utf-8")
        return
    try:
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=240)
        status_path.write_text("reghdfe do-file ran locally; see working/logs/reghdfe_event_tables.log.\n", encoding="utf-8")
    except Exception as exc:
        status_path.write_text(f"reghdfe do-file failed locally: {exc}\n", encoding="utf-8")


def write_expanded_regression_tables(panel: pd.DataFrame) -> None:
    display_headers = [r"$\cdots$"] + [period_label(start, end) for start, end in TABLE_EVENT_PERIODS] + [r"$\cdots$"]
    def write_table(specs, outname):
        tex = [rf"\begin{{tabular}}{{lccc{'r' * len(display_headers)}}}", r"\toprule", r"Measure & $\alpha_i$ & $\lambda_t$ & Ref. & " + " & ".join(display_headers) + r" \\", r"\midrule"]
        rows = []
        for label, col, binary in specs:
            ev = event_period_coefficients(panel, col, prefilter=False, year_fe=True, binary=binary)
            cells, rec = [], {"row_label": label, "treatment": col}
            for start, end in EVENT_PERIODS:
                cur = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
                rec[f"coef_{start}_{end}"] = cur["coef"]; rec[f"se_{start}_{end}"] = cur["se"]; rec[f"p_{start}_{end}"] = cur["p"]
            for start, end in TABLE_EVENT_PERIODS:
                cur = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
                cells.append(period_event_table_cell(cur["coef"], cur["se"], cur["p"], start, bool(cur["reference"])))
            tex.append(label + " & Yes & Yes & " + period_label(*REFERENCE_PERIOD) + " & " + " & ".join([r"$\cdots$"] + cells + [r"$\cdots$"]) + r" \\")
            rows.append(rec)
        tex.extend([r"\bottomrule", r"\end{tabular}", ""])
        pd.DataFrame(rows).to_csv(OUT / "results" / "tables" / f"{outname}.csv", index=False)
        for base in [EXPANDED_OUT, EXPANDED_OVERLEAF]:
            base.mkdir(parents=True, exist_ok=True)
            (base / f"{outname}.tex").write_text("\n".join(tex), encoding="utf-8")
    write_table([
        ("64 kt winds and above", f"{EBTRK_TREAT_PREFIX}_r64_all", True),
        ("50 kt winds and above", f"{EBTRK_TREAT_PREFIX}_r50_all", True),
        ("Top 10% max-rainfall anomaly", "chirps_max_anomaly_top10", True),
        ("Deaths per capita top decile (state-level)", "death_pc_top10_state", True),
    ], "regression_table_expanded_binary")
    write_table([
        ("50 kt municipal coverage share", "ebtrk_share_r50_all", False),
        ("Mahajan-Parag point exposure index (SD)", "mp_x_gjst_z_nofilter", False),
    ], "regression_table_expanded_continuous")



def expanded_specs_for_figures() -> list[tuple[str, str]]:
    return [
        ("64 kt", f"{EBTRK_TREAT_PREFIX}_r64_all"),
        ("50 kt", f"{EBTRK_TREAT_PREFIX}_r50_all"),
        ("Top 10% rain", "chirps_max_anomaly_top10"),
        ("Deaths per capita", "death_pc_top10_state"),
    ]


def plot_expanded_result_figures(panel: pd.DataFrame) -> None:
    specs = expanded_specs_for_figures()
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.6), constrained_layout=True)
    for ax, (title, col) in zip(axes.ravel(), specs):
        ev = event_period_coefficients(panel, col, prefilter=False, year_fe=True, binary=True)
        ax.plot(ev["x"], ev["coef"], color="black", marker="o", markersize=3.0, linewidth=1.2)
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.9)
        ax.axvline(2000, color="#bbbbbb", linestyle=":", linewidth=0.9)
        ax.set_title(title, fontsize=11)
        ax.tick_params(labelsize=8)
        ax.set_xticks(ev["x"])
        ax.set_xticklabels(ev["period"], rotation=35, ha="right")
    axes[0, 0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    axes[1, 0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    fig.suptitle("Expanded two-year dynamic DiD coefficients", fontsize=14)
    for base in [EXPANDED_OUT, EXPANDED_OVERLEAF]:
        base.mkdir(parents=True, exist_ok=True)
        fig.savefig(base / "did_twoyear_expanded_binary.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.6), constrained_layout=True)
    for ax, (title, col) in zip(axes.ravel(), specs):
        ev = event_period_coefficients(panel, col, prefilter=False, year_fe=True, binary=True)
        ev = ev.loc[ev[["period_start", "period_end"]].apply(tuple, axis=1).isin(TABLE_EVENT_PERIODS)].copy()
        ax.fill_between(ev["x"].to_numpy(float), ev["lb"].to_numpy(float), ev["ub"].to_numpy(float), color="#d9d9d9")
        ax.plot(ev["x"], ev["coef"], color="black", marker="o", markersize=3.0, linewidth=1.05)
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.9)
        ax.axvline(2000, color="#bbbbbb", linestyle=":", linewidth=0.9)
        ax.set_title(title, fontsize=11)
        ax.tick_params(labelsize=8)
        ax.set_xticks(ev["x"])
        ax.set_xticklabels(ev["period"], rotation=35, ha="right")
    axes[0, 0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    axes[1, 0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    fig.suptitle("Expanded two-year event-study estimates", fontsize=14)
    for base in [EXPANDED_OUT, EXPANDED_OVERLEAF]:
        fig.savefig(base / "eventstudy_twoyear_expanded_binary.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_results(panel: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.7), constrained_layout=True)
    for ax, threshold in zip(axes, THRESHOLDS):
        col = f"{EBTRK_TREAT_PREFIX}_{threshold}_all"
        ev = event_period_coefficients(panel, col, prefilter=False, year_fe=True, binary=True)
        ax.plot(ev["x"], ev["coef"], color="black", marker="o", markersize=3.0, linewidth=1.2)
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.9)
        ax.axvline(2000, color="#bbbbbb", linestyle=":", linewidth=0.9)
        ax.set_title(THRESHOLD_LABELS[threshold], fontsize=12)
        ax.tick_params(labelsize=8)
        ax.set_xlabel("")
        ax.set_xticks(ev["x"])
        ax.set_xticklabels(ev["period"], rotation=35, ha="right")
    axes[0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    fig.suptitle("Two-year dynamic DiD coefficients: EBTRK threshold treatments", fontsize=14)
    for path in [
        OUT / "results" / "figures" / "did_annual_ebtrk_thresholds.png",
        OUT / "paper_figures" / "did_annual_ebtrk_thresholds.png",
        PAPER_LEGACY / "did_annual_ebtrk_thresholds.png",
    ]:
        fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.7), constrained_layout=True)
    for ax, threshold in zip(axes, THRESHOLDS):
        col = f"{EBTRK_TREAT_PREFIX}_{threshold}_all"
        ev = event_period_coefficients(panel, col, prefilter=False, year_fe=True, binary=True)
        ev = ev.loc[ev[["period_start", "period_end"]].apply(tuple, axis=1).isin(TABLE_EVENT_PERIODS)].copy()
        ax.fill_between(ev["x"].to_numpy(float), ev["lb"].to_numpy(float), ev["ub"].to_numpy(float), color="#d9d9d9")
        ax.plot(ev["x"], ev["coef"], color="black", marker="o", markersize=3.2, linewidth=1.1)
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.9)
        ax.axvline(1999, color="#bbbbbb", linestyle="--", linewidth=0.9)
        ax.set_title(THRESHOLD_LABELS[threshold], fontsize=12)
        ax.tick_params(labelsize=8)
        ax.set_xlabel("")
        ax.set_xticks(ev["x"])
        ax.set_xticklabels(ev["period"], rotation=35, ha="right")
    axes[0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    fig.suptitle("Two-year coefficient estimates: EBTRK threshold treatments", fontsize=14)
    for path in [
        OUT / "results" / "figures" / "eventstudy_annual_ebtrk_thresholds.png",
        OUT / "paper_figures" / "eventstudy_annual_ebtrk_thresholds.png",
        PAPER_LEGACY / "eventstudy_annual_ebtrk_thresholds.png",
        OUT / "results" / "figures" / "eventstudy_twoyear_ebtrk_thresholds.png",
        OUT / "paper_figures" / "eventstudy_twoyear_ebtrk_thresholds.png",
        PAPER_LEGACY / "eventstudy_twoyear_ebtrk_thresholds.png",
    ]:
        fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)



def plot_ntl_support_figures() -> None:
    raw = pd.read_csv(
        ROOT / "raw" / "dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv",
        usecols=["ADM0_NAME", "year", "satellite", "stable_sum"],
    )
    raw = raw.loc[raw["ADM0_NAME"].isin(SELECTED_COUNTRIES)].copy()
    raw["stable_sum"] = pd.to_numeric(raw["stable_sum"], errors="coerce")
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce").astype("Int64")
    country_sat = raw.groupby(["ADM0_NAME", "year", "satellite"], as_index=False)["stable_sum"].sum()
    country_year = country_sat.groupby(["ADM0_NAME", "year"], as_index=False)["stable_sum"].mean()
    colors = {"Belize": "#3366aa", "El Salvador": "#aa6633", "Guatemala": "#228855", "Honduras": "#8844aa", "Nicaragua": "#aa3333"}
    fig, ax = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
    for country in sorted(country_year["ADM0_NAME"].dropna().unique()):
        sub = country_year.loc[country_year["ADM0_NAME"].eq(country)]
        ax.plot(sub["year"], sub["stable_sum"], marker="o", markersize=2.4, linewidth=1.25, label=country, color=colors.get(country))
    ax.axvline(1998, color="#777777", linestyle="--", linewidth=0.9)
    ax.axvline(1999, color="#aaaaaa", linestyle="--", linewidth=0.9)
    ax.set_ylabel("Total stable lights")
    ax.set_xlabel("")
    ax.set_title("Total DMSP-OLS nighttime lights by country")
    ax.legend(frameon=False, fontsize=8, ncols=2)
    ax.tick_params(labelsize=8)
    for path in [OUT / "data" / "figures" / "ntl_total_by_country.png", OUT / "paper_figures" / "ntl_total_by_country.png", PAPER_LEGACY / "ntl_total_by_country.png", PAPER_ROOT / "data" / "ntl_timeseries" / "ntl_total_by_country.png"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    satellite_year = raw.groupby(["satellite", "year"], as_index=False)["stable_sum"].mean()
    mean_year = satellite_year.groupby("year", as_index=False)["stable_sum"].mean()
    palette = ["#3366aa", "#aa6633", "#228855", "#8844aa", "#aa3333", "#666666"]
    fig, ax = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
    ax.plot(mean_year["year"], mean_year["stable_sum"], color="black", linewidth=2.0, marker="o", markersize=2.8, label="Cross-satellite mean", zorder=1)
    for i, satellite in enumerate(sorted(satellite_year["satellite"].dropna().unique())):
        sub = satellite_year.loc[satellite_year["satellite"].eq(satellite)]
        ax.plot(sub["year"], sub["stable_sum"], marker="o", markersize=2.4, linewidth=1.0, label=satellite, color=palette[i % len(palette)], alpha=0.82, zorder=3)
    ax.axvline(1998, color="#777777", linestyle="--", linewidth=0.9)
    ax.axvline(1999, color="#aaaaaa", linestyle="--", linewidth=0.9)
    ax.set_ylabel("Mean stable lights")
    ax.set_xlabel("")
    ax.set_title("Mean DMSP-OLS nighttime lights by satellite")
    ax.legend(frameon=False, fontsize=8, ncols=3)
    ax.tick_params(labelsize=8)
    for path in [OUT / "data" / "figures" / "ntl_mean_by_satellite.png", OUT / "paper_figures" / "ntl_mean_by_satellite.png", PAPER_LEGACY / "ntl_mean_by_satellite.png", PAPER_ROOT / "data" / "ntl_timeseries" / "ntl_mean_by_satellite.png"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)

# -----------------------------------------------------------------------------
# Structured replication-package outputs
# -----------------------------------------------------------------------------
MEASURES = [
    {"slug": "64kt", "label": "64 kt winds", "short_label": "64 kt", "col": f"{EBTRK_TREAT_PREFIX}_r64_all", "binary": True},
    {"slug": "50kt", "label": "50 kt winds", "short_label": "50 kt", "col": f"{EBTRK_TREAT_PREFIX}_r50_all", "binary": True},
    {"slug": "34kt", "label": "34 kt winds", "short_label": "34 kt", "col": f"{EBTRK_TREAT_PREFIX}_r34_all", "binary": True},
    {"slug": "top10_rain_anomaly", "label": "Top 10% max rainfall anomaly", "short_label": "Top 10% rain", "col": "chirps_max_anomaly_top10", "binary": True},
    {"slug": "deaths_per_capita", "label": "Top 10% deaths per c.", "short_label": "Top 10% deaths per c.", "col": "death_pc_top10_state", "binary": True, "panel": "state"},
    {"slug": "50kt_top10_rain_anomaly", "label": "50 kt + top-10% max CHIRPS anomaly", "short_label": "50 kt + top-10% rain", "col": "rain50_chirps_top10", "binary": True},
]
FOUR_TREATMENT_MEASURES = [MEASURES[0], MEASURES[1], MEASURES[3], MEASURES[4]]
SPEC_FOLDERS = [
    ("no_year_fe", False, False, "Unit FE"),
    ("year_fe", True, False, "Unit + Year FE"),
    ("year_fe_ntl_filter", True, True, "Unit + Year FE for pre-Mitch NTL median"),
]
PAPER = PAPER_ROOT
TABLE_SPEC_FOLDERS = [folder for folder in SPEC_FOLDERS if folder[3] != "Unit FE"]
DEATH_STATE_PANEL_CACHE: pd.DataFrame | None = None


def new_output_dirs() -> list[Path]:
    return [
        PAPER / "data" / "summary_tables",
        PAPER / "data" / "ntl_maps",
        PAPER / "data" / "ntl_timeseries",
        PAPER / "data" / "exposure_maps",
        PAPER / "main_results" / "regression_tables" / "did",
        PAPER / "main_results" / "regression_tables" / "event_study",
        PAPER_LEGACY / "main_results" / "figures" / "dynamic_did" / "no_year_fe",
        PAPER_LEGACY / "main_results" / "figures" / "dynamic_did" / "year_fe",
        PAPER_LEGACY / "main_results" / "figures" / "dynamic_did" / "year_fe_ntl_filter",
        PAPER / "main_results" / "figures" / "event_study" / "no_year_fe",
        PAPER / "main_results" / "figures" / "event_study" / "year_fe",
        PAPER / "main_results" / "figures" / "event_study" / "year_fe_ntl_filter",
        PAPER / "robustness" / "regression_tables",
        PAPER / "appendix" / "summary_tables",
        PAPER / "appendix" / "expanded_exposures",
        PAPER / "archive",
        PAPER_LEGACY,
        PAPER / "single_years",
        OUT / "results" / "tables" / "structured",
        OUT / "results" / "figures" / "structured",
    ]


def ensure_structured_dirs() -> None:
    for path in new_output_dirs():
        path.mkdir(parents=True, exist_ok=True)


def write_canonical_processed_files(assignment: pd.DataFrame, panel: pd.DataFrame) -> None:
    processed = WORKING / "data" / "processed"
    assignment.to_csv(processed / "municipality_attributes.csv", index=False)
    ntl = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    ntl["stable_sum"] = pd.to_numeric(ntl["stable_sum"], errors="coerce")
    ntl["log_ntl"] = np.log1p(ntl["stable_sum"])
    ntl.to_csv(processed / "municipality_year_panel.csv", index=False)
    panel.to_csv(processed / "analysis_panel_main.csv", index=False)
    state_panel = build_death_state_panel(assignment)
    state_panel.to_csv(processed / "state_year_panel_deaths.csv", index=False)
    state_out = OUT / "data" / "tables" / "assignment" / "state_year_panel_deaths.csv"
    state_out.parent.mkdir(parents=True, exist_ok=True)
    state_panel.to_csv(state_out, index=False)



def write_reader_summary_table(assignment: pd.DataFrame) -> None:
    sample = assignment.loc[assignment["in_selected_country"].eq(1)].copy()
    pre = sample.loc[
        sample["pre_mean_stable_sum"].notna()
        & sample["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)
    ].copy()
    ntl = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    ntl["stable_sum"] = pd.to_numeric(ntl["stable_sum"], errors="coerce")
    all_vals = ntl.loc[ntl["muni_key"].isin(sample["muni_key"]), "stable_sum"].dropna()
    pre_vals = pd.to_numeric(sample["pre_mean_stable_sum"], errors="coerce").dropna()

    def reader_stats(vals: pd.Series) -> dict[str, float]:
        stats = stat_summary(vals)
        stats["p25"] = float(vals.quantile(0.25))
        stats["p75"] = float(vals.quantile(0.75))
        return stats

    keys = ["mean", "sd", "p10", "p25", "p50", "p75", "p90"]
    dep_all = reader_stats(all_vals)
    dep_pre = reader_stats(pre_vals)
    row_end = " " + chr(92) * 2
    lines = [
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"\multicolumn{8}{l}{\emph{Dependent Variable: Nightlights}}" + row_end,
        "Name & Mean & SD & P10 & P25 & P50 & P75 & P90" + row_end,
        r"\midrule",
    ]
    lines.append(
        "DMSP-OLS stable lights & "
        + " & ".join(summary_tex_number(dep_all[key], 6) for key in keys)
        + row_end
    )
    pre_cells = [summary_tex_number(dep_pre[key], 6) for key in keys]
    pre_cells[keys.index("p50")] = f"{dep_pre['p50']:.2f}"
    lines.append("DMSP-OLS stable lights pre-Mitch & " + " & ".join(pre_cells) + row_end)
    lines.append(r"\addlinespace[0.45em]")
    lines.append(r"\multicolumn{8}{l}{\emph{Independent Variable: Mitch Exposure Measures}}" + row_end)
    lines.append(
        r"Name & Source & Amount treated & "
        r"\begin{tabular}{@{}c@{}}Treated at or above\\pre-Mitch median\end{tabular} & "
        r"Amount control & "
        r"\begin{tabular}{@{}c@{}}Controls at or above\\pre-Mitch median\end{tabular} &  & "
        + row_end
    )
    lines.append(r"\midrule")
    municipal_units = sample["muni_key"].nunique()
    filtered_municipal_units = pre["muni_key"].nunique()
    rows = []
    for name, source, flag_col in [
        ("64 kt winds", "Extended Best Track", f"{EBTRK_TREAT_PREFIX}_r64_all"),
        ("50 kt winds", "Extended Best Track", f"{EBTRK_TREAT_PREFIX}_r50_all"),
        ("34 kt winds", "Extended Best Track", f"{EBTRK_TREAT_PREFIX}_r34_all"),
        ("Top 10% maximum rainfall anomaly", "CHIRPS", "chirps_max_anomaly_top10"),
    ]:
        treated = sample[flag_col].sum()
        treated_filter = pre[flag_col].sum()
        rows.append(
            (
                name,
                source,
                treated,
                treated_filter,
                municipal_units - treated,
                filtered_municipal_units - treated_filter,
                False,
            )
        )
    death_states = build_death_state_panel(assignment).drop_duplicates("state_key")
    retained_death_states = death_states.loc[
        death_states["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)
    ]
    death_treated = death_states["death_pc_top10_state"].sum()
    death_treated_filter = retained_death_states["death_pc_top10_state"].sum()
    rows.append(
        (
            "Top 10% deaths per capita (state*)",
            "Government Reports",
            death_treated,
            death_treated_filter,
            death_states["state_key"].nunique() - death_treated,
            retained_death_states["state_key"].nunique() - death_treated_filter,
            True,
        )
    )
    for name, source, treated, treated_filter, control, control_filter, add_asterisk in rows:
        suffix = "*" if add_asterisk else ""
        numeric_cells = [
            f"{int(value):,}{suffix}"
            for value in [treated, treated_filter, control, control_filter]
        ]
        lines.append(
            f"{tex_escape(name)} & {tex_escape(source)} & "
            + " & ".join(numeric_cells)
            + " & &"
            + row_end
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    tex = "\n".join(lines)
    for path in [PAPER / "data" / "summary_tables" / "table_exposure_summary_reader.tex", OUT / "paper_figures" / "table_exposure_summary_reader.tex"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tex, encoding="utf-8")

def copy_expanded_summary_table() -> None:
    src = OUT / "paper_figures" / "table_exposure_summary_expanded.tex"
    if src.exists():
        dest = PAPER / "appendix" / "summary_tables" / "table_exposure_summary_expanded.tex"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def threshold_swath_geometry(ebtrk: pd.DataFrame, threshold: str):
    return build_bundle_swaths(build_quadrant_swaths(ebtrk)).get((threshold, "ALL"))



def plot_mitch_intro_map(munis_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame) -> None:
    plot_gdf = munis_gdf.loc[munis_gdf["country_name"].isin(SELECTED_COUNTRIES)].copy().to_crs("EPSG:4326")
    country_gdf = plot_gdf.dissolve(by="country_name").reset_index()
    colors = {"r34": "#f4b6b6", "r50": "#df6a63", "r64": "#9f1d20"}
    labels = {"r34": "34 kt", "r50": "50 kt", "r64": "64 kt"}
    bounds = plot_gdf.total_bounds
    fig, ax = plt.subplots(figsize=(9.8, 6.2), constrained_layout=True)
    country_gdf.plot(ax=ax, color="#f7f7f7", edgecolor="#555555", linewidth=0.45, zorder=1)
    for threshold in ["r34", "r50", "r64"]:
        geom = threshold_swath_geometry(ebtrk, threshold)
        if geom is not None:
            gs = gpd.GeoSeries([geom], crs="EPSG:4326")
            gs.plot(ax=ax, color=colors[threshold], alpha={"r34": 0.22, "r50": 0.30, "r64": 0.42}[threshold], edgecolor=colors[threshold], linewidth=1.0, zorder={"r34": 2, "r50": 3, "r64": 4}[threshold])
    track = ebtrk.sort_values("iso_time").dropna(subset=["lon", "lat"])
    ax.plot(track["lon"], track["lat"], color="#005fe8", linewidth=2.1, zorder=7, path_effects=[pe.Stroke(linewidth=3.4, foreground="white"), pe.Normal()])
    ax.scatter(track["lon"], track["lat"], s=10, color="#005fe8", edgecolor="white", linewidth=0.3, zorder=8)
    ax.set_xlim(bounds[0] - 0.9, bounds[2] + 0.9)
    ax.set_ylim(bounds[1] - 0.9, bounds[3] + 0.9)
    ax.set_title("Hurricane Mitch track and EBTRK wind swaths", fontsize=14)
    ax.set_axis_off()
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=colors[t], edgecolor=colors[t], alpha={"r34": .22, "r50": .30, "r64": .42}[t], label=labels[t]) for t in ["r64", "r50", "r34"]]
    handles.append(Patch(facecolor="none", edgecolor="#005fe8", label="Mitch track"))
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.95, fontsize=9)
    for base in [PAPER / "data" / "exposure_maps", OUT / "results" / "figures" / "structured" / "data" / "exposure_maps", OUT / "paper_figures"]:
        base.mkdir(parents=True, exist_ok=True)
        fig.savefig(base / "map_mitch_track_swaths.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

TREAT_RED = "#c9281d"
INCREMENTAL_RED = "#f26b4f"
BASE_MAP_FILL = "#fff7ec"
EXCLUDED_CONTROL_FILL = "#fee8c8"


def _plot_treatment_fill(
    ax,
    plot_gdf: gpd.GeoDataFrame,
    flag_col: str,
    zorder: int = 4,
    retained_col: str | None = None,
) -> list:
    from matplotlib.patches import Patch
    handles = []
    if flag_col not in plot_gdf.columns:
        return handles
    if retained_col is None:
        retained_mask = plot_gdf["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)
        observed_filter = pd.Series(True, index=plot_gdf.index)
    else:
        retained_values = plot_gdf[retained_col]
        retained_mask = retained_values.eq(1).fillna(False)
        observed_filter = retained_values.notna()
    excluded_controls = plot_gdf.loc[
        plot_gdf[flag_col].eq(0) & observed_filter & ~retained_mask
    ].copy()
    treated = plot_gdf.loc[plot_gdf[flag_col].eq(1)].copy()
    treated_retained = retained_mask.reindex(treated.index)
    treated_observed = observed_filter.reindex(treated.index)
    retained = treated.loc[treated_retained]
    dropped = treated.loc[treated_observed & ~treated_retained]
    if not excluded_controls.empty:
        excluded_controls.plot(
            ax=ax,
            color=EXCLUDED_CONTROL_FILL,
            edgecolor="#333333",
            linewidth=0.25,
            zorder=max(2, zorder - 2),
        )
        handles.append(
            Patch(
                facecolor=EXCLUDED_CONTROL_FILL,
                edgecolor="#333333",
                label="Control municipalities excluded by pre-Mitch NTL median filter",
            )
        )
    if not retained.empty:
        retained.plot(ax=ax, color=TREAT_RED, alpha=0.84, edgecolor="#111111", linewidth=0.35, zorder=zorder)
        handles.append(Patch(facecolor=TREAT_RED, edgecolor="#111111", label="Treated and retained"))
    if not dropped.empty:
        dropped.plot(ax=ax, color=INCREMENTAL_RED, alpha=0.88, edgecolor="#111111", linewidth=0.35, zorder=zorder + 1)
        handles.append(Patch(facecolor=INCREMENTAL_RED, edgecolor="#111111", label="Dropped by pre-Mitch NTL median filter"))
    return handles


def plot_single_exposure_map(
    plot_gdf: gpd.GeoDataFrame,
    ebtrk: pd.DataFrame,
    title: str,
    flag_col: str,
    out_path: Path,
    fill: str,
    threshold: str | None = None,
    retained_col: str | None = None,
) -> None:
    bounds = plot_gdf.total_bounds
    xpad = (bounds[2] - bounds[0]) * 0.05
    ypad = (bounds[3] - bounds[1]) * 0.07
    fig, ax = plt.subplots(figsize=(9.6, 6.4), constrained_layout=True)
    plot_gdf.plot(ax=ax, color=BASE_MAP_FILL, edgecolor="#333333", linewidth=0.25, zorder=1)
    if threshold is not None:
        geom = threshold_swath_geometry(ebtrk, threshold)
        if geom is not None:
            gpd.GeoSeries([geom], crs="EPSG:4326").plot(ax=ax, color="#fb6a4a", alpha=0.28, edgecolor="#b30000", linewidth=0.8, zorder=3)
    treatment_handles = _plot_treatment_fill(
        ax,
        plot_gdf,
        flag_col,
        zorder=4,
        retained_col=retained_col,
    )
    track = ebtrk.sort_values("iso_time").dropna(subset=["lon", "lat"])
    ax.plot(track["lon"], track["lat"], color="#005fe8", linewidth=2.0, zorder=7)
    ax.set_title(title, fontsize=14)
    ax.set_xlim(bounds[0] - xpad, bounds[2] + xpad)
    ax.set_ylim(bounds[1] - ypad, bounds[3] + ypad)
    ax.set_axis_off()
    from matplotlib.patches import Patch
    handles = treatment_handles or [Patch(facecolor=TREAT_RED, edgecolor="#111111", label="Municipality treated")]
    if threshold is not None:
        handles.insert(0, Patch(facecolor="#fb6a4a", edgecolor="#b30000", alpha=0.35, label="Exact EBTRK swath"))
    handles.append(Patch(facecolor="none", edgecolor="#005fe8", label="Mitch track"))
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.95, fontsize=9)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def plot_four_treatment_map(plot_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame, out_path: Path) -> None:
    from matplotlib.patches import Patch
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    specs = [
        ("64 kt", f"{EBTRK_TREAT_PREFIX}_r64_all", "r64", None),
        ("50 kt", f"{EBTRK_TREAT_PREFIX}_r50_all", "r50", None),
        ("Top 10% max rainfall", "chirps_max_anomaly_top10", None, None),
        ("Top 10% deaths per c.", "death_pc_top10_state", None, "death_state_filter_retained"),
    ]
    bounds = plot_gdf.total_bounds
    for ax, (title, col, threshold, retained_col) in zip(axes.ravel(), specs):
        plot_gdf.plot(ax=ax, color=BASE_MAP_FILL, edgecolor="#333333", linewidth=0.18)
        if threshold is not None:
            geom = threshold_swath_geometry(ebtrk, threshold)
            if geom is not None:
                gpd.GeoSeries([geom], crs="EPSG:4326").plot(ax=ax, color="#bdbdbd", alpha=0.24, edgecolor="#666666", linewidth=0.7, zorder=3)
        _plot_treatment_fill(
            ax,
            plot_gdf,
            col,
            zorder=4,
            retained_col=retained_col,
        )
        track = ebtrk.sort_values("iso_time").dropna(subset=["lon", "lat"])
        ax.plot(track["lon"], track["lat"], color="#005fe8", linewidth=1.5)
        ax.set_title(title, fontsize=11)
        ax.set_xlim(bounds[0] - 0.8, bounds[2] + 0.8)
        ax.set_ylim(bounds[1] - 0.8, bounds[3] + 0.8)
        ax.set_axis_off()
    fig.suptitle("Four treatment definitions, excluding 34 kt", fontsize=14)
    handles = [
        Patch(facecolor=TREAT_RED, edgecolor="#111111", label="Treated and retained"),
        Patch(facecolor=INCREMENTAL_RED, edgecolor="#111111", label="Dropped by pre-Mitch NTL median filter"),
        Patch(
            facecolor=EXCLUDED_CONTROL_FILL,
            edgecolor="#333333",
            label="Control municipalities excluded by pre-Mitch NTL median filter",
        ),
        Patch(facecolor="#bdbdbd", edgecolor="#666666", alpha=0.35, label="EBTRK swath"),
        Patch(facecolor="none", edgecolor="#005fe8", label="Mitch track"),
    ]
    fig.legend(handles=handles, loc="lower right", bbox_to_anchor=(0.985, 0.02), frameon=True, framealpha=0.96, fontsize=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def plot_structured_exposure_maps(munis_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame) -> None:
    plot_gdf = munis_gdf.loc[munis_gdf["country_name"].isin(SELECTED_COUNTRIES)].copy().to_crs("EPSG:4326")
    if "pre_mean_stable_sum" not in plot_gdf.columns:
        attrs_path = WORKING / "data" / "processed" / "municipality_attributes.csv"
        if attrs_path.exists():
            attrs = pd.read_csv(attrs_path, usecols=["muni_key", "pre_mean_stable_sum"])
            plot_gdf = plot_gdf.merge(attrs, on="muni_key", how="left")
    if "state_key" not in plot_gdf.columns:
        plot_gdf["state_key"] = plot_gdf["country_name"].astype(str) + "|" + plot_gdf["department_name"].astype(str)
    plot_gdf = add_state_impacts(plot_gdf)
    plot_gdf = add_expanded_exposure_flags(plot_gdf)
    death_state_panel = load_death_state_panel().drop_duplicates("state_key")
    death_state_retained = death_state_panel.set_index("state_key")[
        "pre_mean_stable_sum"
    ].ge(PRE_MITCH_NTL_MEDIAN)
    plot_gdf["death_state_filter_retained"] = (
        plot_gdf["state_key"].map(death_state_retained).astype("Int64")
    )
    specs = [
        ("64 kt EBTRK exposure", f"{EBTRK_TREAT_PREFIX}_r64_all", TREAT_RED, "r64", "map_64kt.png", None),
        ("50 kt EBTRK exposure", f"{EBTRK_TREAT_PREFIX}_r50_all", TREAT_RED, "r50", "map_50kt.png", None),
        ("34 kt EBTRK exposure", f"{EBTRK_TREAT_PREFIX}_r34_all", TREAT_RED, "r34", "map_34kt.png", None),
        ("Top 10% max CHIRPS anomaly", "chirps_max_anomaly_top10", TREAT_RED, None, "map_top10_rain_anomaly.png", None),
        ("Top 10% deaths per c.", "death_pc_top10_state", TREAT_RED, None, "map_deaths_per_capita.png", "death_state_filter_retained"),
    ]
    for title, col, color, threshold, filename, retained_col in specs:
        for base in [PAPER / "data" / "exposure_maps", OUT / "results" / "figures" / "structured" / "data" / "exposure_maps"]:
            plot_single_exposure_map(
                plot_gdf,
                ebtrk,
                title,
                col,
                base / filename,
                color,
                threshold,
                retained_col=retained_col,
            )
    for base in [PAPER / "data" / "exposure_maps", OUT / "results" / "figures" / "structured" / "data" / "exposure_maps"]:
        plot_four_treatment_map(plot_gdf, ebtrk, base / "map_four_treatments_no34.png")


def _google_earth_asset() -> Path | None:
    candidates = [
        PAPER / "data" / "ntl_maps" / "GoogleEarth.png",
        WORKING / "overleaf" / "Paper_Figures" / "data" / "ntl_maps" / "GoogleEarth.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in sorted((WORKING / "overleaf" / "Paper_Figures" / "data").glob("**/*Google*Earth*")):
        if candidate.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            return candidate
    return None


def _draw_satellite_mean_panel(ax) -> None:
    raw = pd.read_csv(
        ROOT / "raw" / "dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv",
        usecols=["ADM0_NAME", "year", "satellite", "stable_sum"],
    )
    raw = raw.loc[raw["ADM0_NAME"].isin(SELECTED_COUNTRIES)].copy()
    raw["stable_sum"] = pd.to_numeric(raw["stable_sum"], errors="coerce")
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce")
    satellite_year = raw.groupby(["satellite", "year"], as_index=False)["stable_sum"].mean()
    mean_year = satellite_year.groupby("year", as_index=False)["stable_sum"].mean()
    palette = ["#3366aa", "#aa6633", "#228855", "#8844aa", "#aa3333", "#666666"]
    ax.plot(mean_year["year"], mean_year["stable_sum"], color="black", linewidth=2.0, marker="o", markersize=2.6, label="Cross-satellite mean", zorder=1)
    for i, satellite in enumerate(sorted(satellite_year["satellite"].dropna().unique())):
        sub = satellite_year.loc[satellite_year["satellite"].eq(satellite)]
        ax.plot(sub["year"], sub["stable_sum"], marker="o", markersize=2.2, linewidth=1.0, label=satellite, color=palette[i % len(palette)], alpha=0.86, zorder=3)
    ax.axvline(1998, color="#777777", linestyle="--", linewidth=0.9, zorder=0)
    ax.axvline(1999, color="#aaaaaa", linestyle="--", linewidth=0.9, zorder=0)
    ax.set_ylabel("Mean stable lights")
    ax.set_xlabel("")
    ax.set_title("Mean stable lights by DMSP satellite year", fontsize=12)
    ax.legend(frameon=False, fontsize=8, ncols=4)
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.7)


def _draw_google_earth_panel(ax, df: gpd.GeoDataFrame, country: gpd.GeoDataFrame, bounds: np.ndarray) -> None:
    asset = _google_earth_asset()
    if asset is not None:
        img = Image.open(asset).convert("RGB")
        ax.imshow(img)
        ax.set_title("Google Earth raw lights, 1998", fontsize=12)
        ax.set_axis_off()
        return
    reps = df.representative_point()
    df.plot(ax=ax, color="#181713", edgecolor="none", linewidth=0, zorder=1)
    country.boundary.plot(ax=ax, color="#c9c9c9", linewidth=0.55, zorder=4)
    glow = np.clip(np.log1p(df["stable_sum"].fillna(0)) ** 2.15, 0, 170)
    ax.scatter(reps.x, reps.y, s=glow * 2.8, c="#f2d66b", alpha=0.08, linewidths=0, zorder=2)
    ax.scatter(reps.x, reps.y, s=glow * 1.05, c="#fff2a6", alpha=0.38, linewidths=0, zorder=3)
    ax.scatter(reps.x, reps.y, s=np.clip(glow * 0.28, 0, 34), c="#fff8d8", alpha=0.88, linewidths=0, zorder=5)
    ax.set_title("Google Earth-style raw lights, 1998", fontsize=12)
    ax.set_xlim(bounds[0] - 0.8, bounds[2] + 0.8)
    ax.set_ylim(bounds[1] - 0.8, bounds[3] + 0.8)
    ax.set_facecolor("white")
    ax.set_axis_off()


def plot_ntl_maps(munis_gdf: gpd.GeoDataFrame) -> None:
    from matplotlib.colors import PowerNorm
    plot_gdf = munis_gdf.loc[munis_gdf["country_name"].isin(SELECTED_COUNTRIES)].copy().to_crs("EPSG:4326")
    ntl = pd.read_csv(WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    ntl["stable_sum"] = pd.to_numeric(ntl["stable_sum"], errors="coerce")
    df = plot_gdf.merge(ntl.loc[ntl["year"].eq(1998), ["muni_key", "stable_sum"]], on="muni_key", how="left")
    vals = df["stable_sum"].dropna()
    vmax = float(vals.quantile(0.97)) if len(vals) else 1.0
    bounds = df.total_bounds
    country = df.dissolve(by="country_name").reset_index()

    fig = plt.figure(figsize=(12.2, 9.0), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.82])
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    ax2 = fig.add_subplot(gs[1, :])
    _draw_google_earth_panel(ax0, df, country, bounds)
    df.plot(ax=ax1, column="stable_sum", cmap="viridis", norm=PowerNorm(gamma=0.35, vmin=0, vmax=vmax), legend=True, missing_kwds={"color": "#f2f2f2", "label": "Missing"}, edgecolor="#333333", linewidth=0.15)
    ax1.set_title("Municipality stable-light sums, 1998", fontsize=12)
    ax1.set_xlim(bounds[0] - 0.8, bounds[2] + 0.8)
    ax1.set_ylim(bounds[1] - 0.8, bounds[3] + 0.8)
    ax1.set_axis_off()
    _draw_satellite_mean_panel(ax2)
    fig.suptitle("DMSP-OLS nighttime lights translated to municipalities", fontsize=15)

    fig2, axes = plt.subplots(1, 2, figsize=(12.2, 5.7), constrained_layout=True)
    _draw_google_earth_panel(axes[0], df, country, bounds)
    df.plot(ax=axes[1], column="stable_sum", cmap="viridis", norm=PowerNorm(gamma=0.35, vmin=0, vmax=vmax), legend=True, missing_kwds={"color": "#f2f2f2", "label": "Missing"}, edgecolor="#333333", linewidth=0.15)
    axes[1].set_title("Municipality stable-light sums, 1998", fontsize=12)
    axes[1].set_xlim(bounds[0] - 0.8, bounds[2] + 0.8)
    axes[1].set_ylim(bounds[1] - 0.8, bounds[3] + 0.8)
    axes[1].set_axis_off()
    fig2.suptitle("DMSP-OLS nighttime lights translated to municipalities", fontsize=15)

    for base in [PAPER / "data" / "ntl_maps", OUT / "results" / "figures" / "structured" / "data" / "ntl_maps"]:
        base.mkdir(parents=True, exist_ok=True)
        fig.savefig(base / "ntl_1998_one_page.png", dpi=240, bbox_inches="tight")
        fig2.savefig(base / "ntl_1998_google_two_panel.png", dpi=240, bbox_inches="tight")
    plt.close(fig)
    plt.close(fig2)

def did_table_for_specs(panel: pd.DataFrame, specs: list[dict]) -> str:
    row_end = " " + chr(92) * 2
    lines = [r"\begin{tabular}{llrrrr}", r"\toprule", "Treatment & Specification & Coef. & SE & N & Treated/scale" + row_end, r"\midrule"]
    for spec in specs:
        spec_panel = panel_for_spec(panel, spec)
        for _, year_fe, prefilter, label in TABLE_SPEC_FOLDERS:
            df = spec_panel.loc[spec_panel["pre_mean_stable_sum"].notna()].copy()
            if prefilter:
                df = df.loc[df["pre_mean_stable_sum"].ge(PRE_MITCH_NTL_MEDIAN)].copy()
            r = run_did(df, spec["col"], spec["label"], label, year_fe=year_fe, continuous=not spec.get("binary", True))
            coef = "--" if pd.isna(r.coef) else f"{r.coef:.3f}{star(r.p)}"
            se = "" if pd.isna(r.se) else f"({r.se:.3f})"
            lines.append(" & ".join([tex_escape(spec["label"]), spec_label_tex(label), coef, se, fmt(r.n, 0), fmt(r.treated_units, 3 if not spec.get("binary", True) else 0)]) + row_end)
        if spec is not specs[-1]:
            lines.append(r"\addlinespace")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def event_table_for_specs(
    panel: pd.DataFrame,
    specs: list[dict],
    table_spec_folders: list[tuple[str, bool, bool, str]] | None = None,
) -> str:
    if table_spec_folders is None:
        table_spec_folders = TABLE_SPEC_FOLDERS
    row_end = " " + chr(92) * 2
    headers = [table_period_label(start, end) for start, end in TABLE_OUTPUT_PERIODS]
    lines = [rf"\begin{{tabular}}{{ll{'r' * len(headers)}}}", r"\toprule", "Treatment & Specification & " + " & ".join(headers) + row_end, r"\midrule"]
    for spec in specs:
        first = True
        short = spec.get("short_label", spec["label"])
        spec_panel = panel_for_spec(panel, spec)
        for _, year_fe, prefilter, label in table_spec_folders:
            ev = event_period_coefficients(spec_panel, spec["col"], prefilter=prefilter, year_fe=year_fe, binary=spec.get("binary", True))
            cells = []
            for start, end in TABLE_OUTPUT_PERIODS:
                cur = ev.loc[ev["period_start"].eq(start) & ev["period_end"].eq(end)].iloc[0]
                cells.append(period_event_table_cell(cur["coef"], cur["se"], cur["p"], start, bool(cur["reference"])))
            treat_cell = tex_escape(short) if first else ""
            lines.append(" & ".join([treat_cell, spec_label_tex(label)] + cells) + row_end)
            first = False
        if spec is not specs[-1]:
            lines.append(r"\addlinespace")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)

def write_structured_regression_tables(panel: pd.DataFrame) -> None:
    table_specs = MEASURES + [{"slug": "four_treatments_no34", "label": "Four treatments excluding 34 kt", "col": "", "binary": True}]
    for spec in table_specs:
        specs = FOUR_TREATMENT_MEASURES if spec["slug"] == "four_treatments_no34" else [spec]
        for folder, tex in [("did", did_table_for_specs(panel, specs)), ("event_study", event_table_for_specs(panel, specs))]:
            for base in [PAPER / "main_results" / "regression_tables" / folder, OUT / "results" / "tables" / "structured" / "main_results" / "regression_tables" / folder]:
                base.mkdir(parents=True, exist_ok=True)
                (base / f"table_{spec['slug']}.tex").write_text(tex, encoding="utf-8")


    unit_fe_tex = event_table_for_specs(panel, FOUR_TREATMENT_MEASURES, table_spec_folders=[SPEC_FOLDERS[0]])
    for base in [
        PAPER / "appendix" / "regression_tables",
        OUT / "results" / "tables" / "structured" / "appendix" / "regression_tables",
    ]:
        base.mkdir(parents=True, exist_ok=True)
        (base / "table_four_treatments_no34_unit_fe.tex").write_text(unit_fe_tex, encoding="utf-8")


def plot_dynamic_measure(panel: pd.DataFrame, specs: list[dict], title: str, path: Path, prefilter: bool, year_fe: bool) -> None:
    n = len(specs)
    ncols = 2 if n == 4 else n
    nrows = 2 if n == 4 else 1
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.0 * ncols, 3.9 * nrows), squeeze=False, constrained_layout=True)
    for ax, spec in zip(axes.ravel(), specs):
        spec_panel = panel_for_spec(panel, spec)
        s = did_period_series(spec_panel, spec["col"], prefilter=prefilter, year_fe=year_fe)
        for val, style, label in [(1.0, "-", "Treated"), (0.0, "--", "Control")]:
            sub = s.loc[s["treated"].eq(val)]
            if not sub.empty:
                ax.plot(sub["period_start"], sub["adj"], style, color="black" if val == 1 else "#777777", linewidth=1.25, label=label)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.8)
        ax.axvline(2000, color="#bbbbbb", linestyle=":", linewidth=0.8)
        ax.set_title(spec["label"], fontsize=10)
        ticks = s[["period_start", "period"]].drop_duplicates().sort_values("period_start")
        ax.set_xticks(ticks["period_start"])
        ax.set_xticklabels(ticks["period"], rotation=35, ha="right", fontsize=7)
        ax.tick_params(labelsize=8)
    for ax in axes.ravel()[len(specs):]:
        ax.set_axis_off()
    ylabel = "FE-adjusted two-year mean log(1 + stable lights)" if year_fe else "Two-year mean log(1 + stable lights)"
    axes.ravel()[0].set_ylabel(ylabel, fontsize=9)
    axes.ravel()[0].legend(fontsize=8, frameon=False)
    fig.suptitle(title, fontsize=13)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_event_measure(
    panel: pd.DataFrame,
    specs: list[dict],
    title: str,
    path: Path,
    year_fe: bool,
    prefilter: bool,
    sample_filter: str | None = None,
) -> None:
    n = len(specs)
    ncols = 2 if n == 4 else n
    nrows = 2 if n == 4 else 1
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.0 * ncols, 3.9 * nrows), squeeze=False, constrained_layout=True)
    for ax, spec in zip(axes.ravel(), specs):
        spec_panel = panel_for_spec(panel, spec)
        if sample_filter == "pre_ntl_snr":
            spec_panel = filter_panel_by_pre_ntl_snr(spec_panel)
        elif sample_filter is not None:
            raise ValueError(f"Unknown event-study sample filter: {sample_filter}")
        ev = event_period_coefficients(spec_panel, spec["col"], prefilter=prefilter, year_fe=year_fe, binary=spec.get("binary", True))
        ev = ev.loc[ev[["period_start", "period_end"]].apply(tuple, axis=1).isin(TABLE_EVENT_PERIODS)].copy()
        ax.fill_between(ev["x"].to_numpy(float), ev["lb"].to_numpy(float), ev["ub"].to_numpy(float), color="#d9d9d9")
        ax.plot(ev["x"], ev["coef"], color="black", marker="o", markersize=3.0, linewidth=1.05)
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.8)
        ax.axvline(2000, color="#bbbbbb", linestyle=":", linewidth=0.8)
        ax.set_title(spec["label"], fontsize=10)
        ax.set_xticks(ev["x"])
        ax.set_xticklabels(ev["period"], rotation=35, ha="right", fontsize=7)
    for ax in axes.ravel()[len(specs):]:
        ax.set_axis_off()
    axes.ravel()[0].set_ylabel("Coefficient relative to 1996-1997", fontsize=9)
    fig.suptitle(title, fontsize=13)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)

def write_structured_main_figures(panel: pd.DataFrame) -> None:
    fig_specs = MEASURES + [{"slug": "four_treatments_no34", "label": "Four treatments excluding 34 kt", "col": "", "binary": True}]
    for folder, year_fe, prefilter, label in SPEC_FOLDERS:
        for spec in fig_specs:
            specs = FOUR_TREATMENT_MEASURES if spec["slug"] == "four_treatments_no34" else [spec]
            for base in [PAPER_LEGACY / "main_results" / "figures" / "dynamic_did" / folder, OUT / "results" / "figures" / "structured" / "legacy" / "main_results" / "figures" / "dynamic_did" / folder]:
                plot_dynamic_measure(panel, specs, f"Dynamic DiD: {label}", base / f"fig_{spec['slug']}.png", prefilter=prefilter, year_fe=year_fe)
            for base in [PAPER / "main_results" / "figures" / "event_study" / folder, OUT / "results" / "figures" / "structured" / "main_results" / "figures" / "event_study" / folder]:
                plot_event_measure(panel, specs, f"Event study: {label}", base / f"fig_{spec['slug']}.png", year_fe=year_fe, prefilter=prefilter)


def write_snr_event_study_figure(panel: pd.DataFrame) -> None:
    for base in [
        PAPER / "robustness" / "figures" / "event_study" / "year_fe_snr_filter",
        OUT / "results" / "figures" / "structured" / "robustness" / "figures" / "event_study" / "year_fe_snr_filter",
    ]:
        plot_event_measure(
            panel,
            FOUR_TREATMENT_MEASURES,
            "Event study: Unit + Year FE for pre-Mitch NTL mean / SD >= 1",
            base / "fig_four_treatments_no34.png",
            year_fe=True,
            prefilter=False,
            sample_filter="pre_ntl_snr",
        )


def write_robustness_tables(panel: pd.DataFrame) -> None:
    besttrack_specs = [
        {"slug": "share64", "label": "64 kt area share", "short_label": "64 kt share", "col": "ebtrk_share_r64_all", "binary": False},
        {"slug": "share50", "label": "50 kt area share", "short_label": "50 kt share", "col": "ebtrk_share_r50_all", "binary": False},
        {"slug": "share34", "label": "34 kt area share", "short_label": "34 kt share", "col": "ebtrk_share_r34_all", "binary": False},
    ]
    mp_specs = [
        {"slug": "mp", "label": "Mahajan-Parag exposure index (SD)", "short_label": "Mahajan-Parag", "col": "mp_x_gjst_z_nofilter", "binary": False},
    ]
    outputs = {
        "table_continuous_besttrack.tex": event_table_for_specs(panel, besttrack_specs),
        "table_continuous_mahajan_parag.tex": event_table_for_specs(panel, besttrack_specs + mp_specs),
    }
    for filename, tex in outputs.items():
        for base in [PAPER / "robustness" / "regression_tables", OUT / "results" / "tables" / "structured" / "robustness" / "regression_tables"]:
            base.mkdir(parents=True, exist_ok=True)
            (base / filename).write_text(tex, encoding="utf-8")

def copy_structured_time_series() -> None:
    pairs = {"ntl_total_by_country.png": PAPER / "data" / "ntl_timeseries" / "ntl_total_by_country.png", "ntl_mean_by_satellite.png": PAPER / "data" / "ntl_timeseries" / "ntl_mean_by_satellite.png"}
    for name, dest in pairs.items():
        for src in [PAPER / name, PAPER_LEGACY / name]:
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                break


def annual_year_label(year: int) -> str:
    return f"{str(year)[-2:]}'"


def annual_event_table_cell(coef: float, se: float, p: float, year: int, reference: bool = False) -> str:
    if reference:
        return "ref."
    if pd.isna(coef):
        return "--"
    txt = f"{coef:.3f}{star(p)}"
    if pd.notna(se):
        txt = "\\begin{tabular}{@{}c@{}}" + txt + "\\\\{\\scriptsize (" + f"{se:.3f}" + ")}\\end{tabular}"
    if year >= 1998 and coef < 0:
        return rf"\cellcolor{{{shade_for_significance(p)}}}{txt}"
    return txt


def single_year_table_for_specs(panel: pd.DataFrame, specs: list[dict]) -> str:
    row_end = " " + chr(92) * 2
    years = EVENT_TABLE_YEARS
    lines = [rf"\begin{{tabular}}{{ll{'r' * len(years)}}}", r"\toprule", "Treatment & Specification & " + " & ".join(annual_year_label(y) for y in years) + row_end, r"\midrule"]
    for spec in specs:
        first = True
        short = spec.get("short_label", spec["label"])
        spec_panel = panel_for_spec(panel, spec)
        for _, year_fe, prefilter, label in TABLE_SPEC_FOLDERS:
            ev = event_coefficients(spec_panel, spec["col"], prefilter=prefilter, year_fe=year_fe)
            cells = []
            for year in years:
                cur = ev.loc[ev["year"].eq(year)].iloc[0]
                cells.append(annual_event_table_cell(cur["coef"], cur["se"], cur["p"], year, bool(cur["reference"])))
            treat_cell = tex_escape(short) if first else ""
            lines.append(" & ".join([treat_cell, spec_label_tex(label)] + cells) + row_end)
            first = False
        if spec is not specs[-1]:
            lines.append(r"\addlinespace")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def single_year_continuous_mp_table(panel: pd.DataFrame) -> str:
    row_end = " " + chr(92) * 2
    years = EVENT_TABLE_YEARS
    rows = [
        ("Mahajan-Parag exposure index (SD)", "mp_x_gjst_z_nofilter", False, "Unit + Year FE"),
        ("", "mp_x_gjst_z_prefilter", True, "Unit + Year FE for pre-Mitch NTL median"),
    ]
    lines = [rf"\begin{{tabular}}{{ll{'r' * len(years)}}}", r"\toprule", "Treatment & Specification & " + " & ".join(annual_year_label(y) for y in years) + row_end, r"\midrule"]
    for treatment, col, prefilter, label in rows:
        ev = event_series(panel, col, continuous=True, prefilter=prefilter, year_fe=True)
        ev = ev.loc[ev["year"].isin(years)].copy()
        cells = []
        for year in years:
            cur = ev.loc[ev["year"].eq(year)].iloc[0]
            cells.append(annual_event_table_cell(cur["coef"], cur["se"], np.nan, year, bool(cur["reference"])))
        lines.append(" & ".join([treatment, spec_label_tex(label)] + cells) + row_end)
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def plot_single_year_event_measure(panel: pd.DataFrame, specs: list[dict], title: str, path: Path, prefilter: bool = True) -> None:
    n = len(specs)
    ncols = 2 if n == 4 else n
    nrows = 2 if n == 4 else 1
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.0 * ncols, 3.9 * nrows), squeeze=False, constrained_layout=True)
    for ax, spec in zip(axes.ravel(), specs):
        spec_panel = panel_for_spec(panel, spec)
        ev = event_series(spec_panel, spec["col"], continuous=not spec.get("binary", True), prefilter=prefilter, year_fe=True)
        ev = ev.loc[ev["year"].isin(EVENT_TABLE_YEARS)].copy()
        ax.fill_between(ev["year"].to_numpy(float), ev["lb"].to_numpy(float), ev["ub"].to_numpy(float), color="#d9d9d9")
        ax.plot(ev["year"], ev["coef"], color="black", marker="o", markersize=3.0, linewidth=1.05)
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.8)
        ax.axvline(1999, color="#bbbbbb", linestyle=":", linewidth=0.8)
        ax.set_title(spec["label"], fontsize=10)
        ax.set_xticks(ev["year"])
        ax.set_xticklabels([annual_year_label(int(y)) for y in ev["year"]], rotation=35, ha="right", fontsize=7)
        ax.tick_params(labelsize=8)
    for ax in axes.ravel()[len(specs):]:
        ax.set_axis_off()
    axes.ravel()[0].set_ylabel("Coefficient relative to 1997", fontsize=9)
    fig.suptitle(title, fontsize=13)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_single_year_outputs(panel: pd.DataFrame) -> None:
    single_dirs = [PAPER / "single_years", OUT / "paper_figures" / "single_years"]
    tex = single_year_table_for_specs(panel, FOUR_TREATMENT_MEASURES)
    write_text_outputs(
        [base / "regression_table_four_treatments_no34.tex" for base in single_dirs],
        tex,
    )
    for base in single_dirs:
        plot_single_year_event_measure(
            panel,
            FOUR_TREATMENT_MEASURES,
            "Single-year event-study robustness",
            base / "eventstudy_annual_four_treatments_no34.png",
            prefilter=True,
        )


def copy_appendix_expanded_outputs() -> None:
    old = EXPANDED_OVERLEAF
    new = PAPER / "appendix" / "expanded_exposures"
    if old.exists():
        new.mkdir(parents=True, exist_ok=True)
        for src in old.iterdir():
            if src.is_file():
                shutil.copy2(src, new / src.name)


def create_recovery_hypotheses_figure() -> None:
    x = np.linspace(0, 10, 220)
    baseline = 0.42 * x + 2.0
    event = 3.0
    def smoothstep(z):
        return 1 / (1 + np.exp(-2.2 * z))
    creative = baseline + 2.2 * smoothstep(x - event - 1.0)
    build_back = baseline + 1.45 * smoothstep(x - event - 2.8)
    recover = baseline - 0.55 * np.exp(-0.5 * (x - event - 1.6) ** 2)
    no_recovery = baseline - 1.25 * smoothstep(x - event - 0.7)
    fig, ax = plt.subplots(figsize=(7.0, 4.3), constrained_layout=True)
    ax.axvspan(event - 0.28, event + 0.28, color="#d9d9d9", zorder=0)
    ax.text(event + 0.02, baseline.max() + 0.95, "disaster", rotation=90, va="top", ha="center", fontsize=10)
    ax.plot(x[x <= event], baseline[x <= event], color="black", linewidth=2.0)
    ax.plot(x, baseline, color="black", linewidth=1.7)
    for y, color in [(creative, "#aeb4bb"), (build_back, "#8f969c"), (recover, "#555555"), (no_recovery, "#777777")]:
        ax.plot(x[x >= event], y[x >= event], color=color, linewidth=2.0)
    labels = [(creative, '"Creative destruction"', 0.92), (build_back, '"Build back better"', 0.78), (recover, '"Recovery to trend"', 0.63), (no_recovery, '"No recovery"', 0.45)]
    for y, label, frac in labels:
        idx = int(frac * (len(x) - 1))
        ax.annotate(label, xy=(x[idx], y[idx]), xytext=(10.5, y[idx]), ha="left", va="center", fontsize=10, arrowprops={"arrowstyle": "-", "color": "#9a9a9a", "lw": 1.1})
    ax.annotate("", xy=(10.6, 1.3), xytext=(0.35, 1.3), arrowprops={"arrowstyle": "->", "color": "black"})
    ax.annotate("", xy=(0.55, 7.45), xytext=(0.55, 1.25), arrowprops={"arrowstyle": "->", "color": "black"})
    ax.text(5.4, 0.78, "Time", ha="center", va="center", fontsize=12)
    ax.text(0.05, 4.5, "GDP per capita", rotation=90, ha="center", va="center", fontsize=12)
    ax.text(1.25, baseline[np.searchsorted(x, 1.25)] + 0.25, "baseline\ntrend", ha="left", va="center", fontsize=10)
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0.7, 7.8)
    ax.axis("off")
    for base in [PAPER / "data" / "literature", OUT / "paper_figures"]:
        base.mkdir(parents=True, exist_ok=True)
        fig.savefig(base / "recovery_hypotheses.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def create_exposure_reveal_figures() -> None:
    srcs = [PAPER / "data" / "exposure_maps" / "map_64kt.png", PAPER / "data" / "exposure_maps" / "map_50kt.png", PAPER / "data" / "exposure_maps" / "map_top10_rain_anomaly.png", PAPER / "data" / "exposure_maps" / "map_deaths_per_capita.png"]
    imgs = [Image.open(path).convert("RGB") for path in srcs]
    tile_w = min(img.width for img in imgs)
    tile_h = min(img.height for img in imgs)
    imgs = [ImageOps.fit(img, (tile_w, tile_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)) for img in imgs]
    blank = Image.new("RGB", (tile_w, tile_h), "white")
    draw_blank = ImageDraw.Draw(blank)
    draw_blank.rectangle([18, 18, tile_w - 18, tile_h - 18], outline="#d0d0d0", width=3)
    layouts = [[imgs[0], imgs[1], blank, blank], [imgs[0], imgs[1], imgs[2], blank], imgs]
    outdir = PAPER / "presentation"
    outdir.mkdir(parents=True, exist_ok=True)
    for idx, layout in enumerate(layouts, start=2):
        canvas = Image.new("RGB", (tile_w * 2, tile_h * 2), "white")
        for j, img in enumerate(layout):
            canvas.paste(img, ((j % 2) * tile_w, (j // 2) * tile_h))
        canvas.save(outdir / f"exposure_reveal_{idx}.png")


def create_presentation_assets() -> None:
    create_recovery_hypotheses_figure()
    create_exposure_reveal_figures()


def write_presentation() -> None:
    tex = r'''
\documentclass[aspectratio=169]{beamer}
\mode<presentation>{
  \usetheme{default}
  \usecolortheme{default}
  \usefonttheme{default}
  \setbeamertemplate{navigation symbols}{}
  \setbeamertemplate{caption}[numbered]
}
\usepackage[english]{babel}
\usepackage[utf8]{inputenc}
\usepackage{booktabs}
\usepackage[table]{xcolor}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{tikz}
\newcommand{\greytext}[1]{{\color{gray!55}#1}}
\title[Years Lost to Mitch]{The Years Lost to Mitch}
\author{Orlando Valladares}
\institute{ECON 64}
\date{\today}
\begin{document}

\begin{frame}{Introduction}
\centering
\Large How much local economic activity was lost after Hurricane Mitch?
\end{frame}

\begin{frame}{Introduction}
\centering
\Large \greytext{How much local economic activity was lost after Hurricane Mitch?}
\vspace{0.8cm}
\normalsize
\begin{itemize}
\item Economic impact of disasters is a motivating concern for developing countries: how much can be lost informs how much should be sent, and climate change will lead to heightened frequency.
\item However: causal intervention and data availability remain difficult.
\end{itemize}
\end{frame}

\begin{frame}{Research Question}
\centering
\Large \greytext{How much local economic activity was lost after Hurricane Mitch in 1998?}
\vspace{0.45cm}
\normalsize
\begin{itemize}\color{gray!55}
\item Increases because of climate change (Knutson 2020, Garner 2023), how much may be lost informs how much should be spent.
\item However: causal intervention and data availability remain difficult.
\end{itemize}
\vspace{0.55cm}
\Large Using satellite and meteorological data, what was the impact and recovery of 1998's Hurricane Mitch exposure to nightlights across Central American municipalities?
\end{frame}

\begin{frame}{Literature}
\begin{columns}[T,totalwidth=\linewidth]
\begin{column}{0.54\linewidth}
\begin{enumerate}
\item \textbf{Economic impact of disasters.} Recovery paths range from creative destruction to no recovery.
\item \textbf{Meta discussions on measuring disasters.}
\item \textbf{Hurricane Mitch.} Honduran and small rural survey focused, showing losses but narrow.
\end{enumerate}
\end{column}
\begin{column}{0.44\linewidth}
\centering
\includegraphics[width=\linewidth]{Paper_Figures/data/literature/recovery_hypotheses.png}
\end{column}
\end{columns}
\end{frame}

\begin{frame}{Context}
\begin{columns}[T,totalwidth=\linewidth]
\begin{column}{0.64\linewidth}
\centering
\includegraphics[width=\linewidth,height=0.86\textheight,keepaspectratio]{Paper_Figures/data/exposure_maps/map_mitch_track_swaths.png}
\end{column}
\begin{column}{0.34\linewidth}
\centering
\includegraphics[width=\linewidth,height=0.34\textheight,keepaspectratio]{Paper_Figures/presentation/Guanaja.jpg}

{\scriptsize Damage in Guanaja, Northern Honduras}

\vspace{0.25cm}
\includegraphics[width=\linewidth,height=0.34\textheight,keepaspectratio]{Paper_Figures/presentation/Tegucigalpa.jpg}

{\scriptsize Damage in Tegucigalpa, concentrated along river}
\end{column}
\end{columns}
\end{frame}

\begin{frame}{Night Lights}
\centering
\includegraphics[width=0.98\linewidth]{Paper_Figures/data/ntl_maps/ntl_1998_google_two_panel.png}
\end{frame}

\begin{frame}{Night Lights}
\centering
\includegraphics[height=0.88\textheight,keepaspectratio]{Paper_Figures/data/ntl_maps/ntl_1998_one_page.png}
\end{frame}

\begin{frame}{Mitch Exposure}
\centering
\includegraphics[height=0.88\textheight]{Paper_Figures/presentation/exposure_reveal_2.png}
\end{frame}

\begin{frame}{Mitch Exposure}
\centering
\includegraphics[height=0.88\textheight]{Paper_Figures/presentation/exposure_reveal_3.png}
\end{frame}

\begin{frame}{Mitch Exposure}
\centering
\includegraphics[height=0.88\textheight]{Paper_Figures/presentation/exposure_reveal_4.png}
\end{frame}

\begin{frame}{Design}
\centering
\Large
\[
\log(1+NTL_{it})=\sum_{\substack{\tau=92'\text{--}93'\\ \tau\neq 96'\text{--}97'}}^{12'\text{--}13'}\beta_\tau\left(Exposure_i^{1998}\times \mathbf{1}[t\in\tau]\right)+\alpha_i+\lambda_t+\varepsilon_{it}
\]
\vspace{0.35cm}
\normalsize
\begin{itemize}
\item $i$ is usually a municipality; for deaths per capita, exposure is state/department-level.
\item $t$ is taken in two-year bins.
\end{itemize}
\end{frame}

\begin{frame}{Results: (i) Timing (ii) Magnitudes}
\centering
\textbf{Timing}
\vspace{0.05cm}
\includegraphics[height=0.76\textheight,keepaspectratio]{Paper_Figures/main_results/figures/event_study/year_fe_ntl_filter/fig_four_treatments_no34.png}
\end{frame}

\begin{frame}{Results: (i) Timing (ii) Magnitudes}
\begin{columns}[T,totalwidth=\linewidth]
\begin{column}{0.70\linewidth}
\centering
\includegraphics[width=\linewidth]{Paper_Figures/main_results/figures/event_study/year_fe_ntl_filter/fig_four_treatments_no34.png}
\end{column}
\begin{column}{0.27\linewidth}
\small
\textbf{Magnitudes}

\vspace{0.25cm}
Two stages:
\begin{itemize}
\item Roughly a 10\% drop in the first phase.
\item Roughly a 20\% drop in the second phase.
\end{itemize}

\vspace{0.2cm}
\footnotesize Relative to the 1996--1997 gap.
\end{column}
\end{columns}
\end{frame}

\begin{frame}{Conclusion}
\small
\begin{itemize}
\item \only<1>{Ishizawa identifies an elasticity of real GDP to NTL between 0.158 and 0.233 in Central America in my study period.}\only<2->{\greytext{Ishizawa identifies an elasticity of real GDP to NTL between 0.158 and 0.233 in Central America in my study period.}}
\item \only<1>{\greytext{Taking my losses, this implies a two-phase local income drop of 1.60\%--2.40\% and 3.24\%--4.78\%, which municipalities could calculate.}}\only<2>{Taking my losses, this implies a two-phase local income drop of 1.60\%--2.40\% and 3.24\%--4.78\%, which municipalities could calculate.}\only<3->{\greytext{Taking my losses, this implies a two-phase local income drop of 1.60\%--2.40\% and 3.24\%--4.78\%, which municipalities could calculate.}}
\item \only<1-2>{\greytext{Limitations to the study remain: ``Top 10\% max rainfall anomaly is not a good proxy for flooding. I would change it.''}}\only<3>{Limitations to the study remain: ``Top 10\% max rainfall anomaly is not a good proxy for flooding. I would change it.''}\only<4->{\greytext{Limitations to the study remain: ``Top 10\% max rainfall anomaly is not a good proxy for flooding. I would change it.''}}
\item \only<1-3>{\greytext{Hurricanes do not care about municipality boundaries; continuous exposure variables may be better, though harder to interpret.}}\only<4>{Hurricanes do not care about municipality boundaries; continuous exposure variables may be better, though harder to interpret.}\only<5->{\greytext{Hurricanes do not care about municipality boundaries; continuous exposure variables may be better, though harder to interpret.}}
\item \only<1-4>{\greytext{Other hurricanes could now be added, like Eta and Iota (2023), and impact better calculated with VIIRS night lights.}}\only<5>{Other hurricanes could now be added, like Eta and Iota (2023), and impact better calculated with VIIRS night lights.}
\end{itemize}
\end{frame}

\appendix

\begin{frame}{Did treated municipalities show reductions too? Not clearly}
\centering
\includegraphics[height=0.84\textheight,keepaspectratio]{Paper_Figures/data/ntl_timeseries/ntl_total_by_country.png}
\end{frame}

\begin{frame}{Why is the gap in the second phase worse}
\centering
\includegraphics[height=0.84\textheight,keepaspectratio]{Paper_Figures/single_years/eventstudy_annual_four_treatments_no34.png}
\end{frame}

\begin{frame}{Appendix: Summary Statistics}
\centering
\scriptsize
\resizebox{0.98\linewidth}{!}{\input{Paper_Figures/data/summary_tables/table_exposure_summary_reader.tex}}
\end{frame}

\begin{frame}{Appendix: Regression Table}
\centering
\scriptsize
\resizebox{0.98\linewidth}{!}{\input{Paper_Figures/main_results/regression_tables/event_study/table_four_treatments_no34.tex}}
\end{frame}

\begin{frame}{Appendix: Unit FE Dynamic DiD}
\centering
\includegraphics[height=0.84\textheight,keepaspectratio]{Paper_Figures/legacy/main_results/figures/dynamic_did/no_year_fe/fig_four_treatments_no34.png}
\end{frame}

\end{document}
'''.lstrip()
    (WORKING / "overleaf" / "presentation.tex").write_text(tex, encoding="utf-8")

def build_structured_outputs(munis_gdf: gpd.GeoDataFrame, ebtrk: pd.DataFrame, assignment: pd.DataFrame, panel: pd.DataFrame) -> None:
    ensure_structured_dirs()
    write_canonical_processed_files(assignment, panel)
    write_reader_summary_table(assignment)
    copy_expanded_summary_table()
    plot_mitch_intro_map(munis_gdf, ebtrk)
    plot_structured_exposure_maps(munis_gdf, ebtrk)
    plot_ntl_maps(munis_gdf)
    copy_structured_time_series()
    write_structured_regression_tables(panel)
    write_structured_main_figures(panel)
    write_snr_event_study_figure(panel)
    write_single_year_outputs(panel)
    write_robustness_tables(panel)
    create_presentation_assets()
    copy_appendix_expanded_outputs()
    write_presentation()

def copy_existing_support_files() -> None:
    plot_ntl_support_figures()


def main() -> None:
    ensure_dirs()
    ebtrk = load_mitch_ebtrk()
    munis = load_municipalities()
    munis = attach_audited_ebtrk_exposures(munis)
    assignment = build_assignment(munis)
    build_summary_tables(assignment)
    write_raw_mahajan_summary()
    plot_ebtrk_maps(munis, ebtrk)
    plot_expanded_maps(munis, ebtrk)
    panel = build_panel(assignment)
    write_reghdfe_bridge(panel)
    run_regressions(panel)
    write_expanded_regression_tables(panel)
    plot_results(panel)
    plot_expanded_result_figures(panel)
    copy_existing_support_files()
    build_structured_outputs(munis, ebtrk, assignment, panel)
    print("Built assignment, canonical panels, structured Overleaf assets, maps, figures, and regression tables.")


if __name__ == "__main__":
    main()
