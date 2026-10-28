from __future__ import annotations

import base64
import json
import math
import sys
import re
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

from pipeline_config import EXTERNAL_DIR, PROCESSED_DIR, RAW_DIR, WEB_DIR, output_path


DID_DIR = PROCESSED_DIR / "did_dashboard"
DEFAULT_OUTPUT = Path("out") / "Mitch_integrated_dashboard.html"
NTL_RAW = RAW_DIR / "dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv"
STATE_IMPACTS_RAW = RAW_DIR / "mitch_subnational_impacts.csv"
YANG_PARAG_RAW = RAW_DIR / "orlando_custom_mitch.xlsx"
YANG_PARAG_GRID_CSV = DID_DIR / "yang_parag_mitch_grid.csv"
YANG_PARAG_GRID_GEOJSON = WEB_DIR / "yang_parag_mitch_grid.geojson"
YANG_GRID_STEP_DEGREES = 0.25
YANG_WIND_THRESHOLD_KT = 33.0

CENTRAL_AMERICA_GRID_COUNTRIES = {
    "BLZ": "Belize",
    "GTM": "Guatemala",
    "SLV": "El Salvador",
    "HND": "Honduras",
    "NIC": "Nicaragua",
    "CRI": "Costa Rica",
    "PAN": "Panama",
}
CENTRAL_AMERICA_COUNTRY_SET = set(CENTRAL_AMERICA_GRID_COUNTRIES.values())


def read_json(path: Path) -> object:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def clean_json(payload: object) -> object:
    if isinstance(payload, dict):
        return {k: clean_json(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [clean_json(v) for v in payload]
    if isinstance(payload, float) and (math.isnan(payload) or math.isinf(payload)):
        return None
    return payload


def safe_json(payload: object) -> str:
    return json.dumps(clean_json(payload), ensure_ascii=False, separators=(",", ":"))


def numeric_or_none(value: object) -> float | None:
    out = pd.to_numeric(value, errors="coerce")
    if pd.isna(out):
        return None
    return float(out)


def csv_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")
    df = pd.read_csv(path, low_memory=False, keep_default_na=False)
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


def normalize_admin_name(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"^comarca\s+", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def state_impact_records(municipalities: dict[str, object]) -> list[dict[str, object]]:
    if not STATE_IMPACTS_RAW.exists():
        return []
    states = {}
    for feature in municipalities.get("features", []):
        props = feature.get("properties", {})
        country = props.get("country_name")
        state = props.get("department_name")
        if not country or not state:
            continue
        norm_key = f"{normalize_admin_name(country)}|{normalize_admin_name(state)}"
        states[norm_key] = {
            "state_key": f"{country}|{state}",
            "country_name": country,
            "department_name": state,
        }
    df = pd.read_csv(STATE_IMPACTS_RAW, encoding="utf-8", low_memory=False)
    records: list[dict[str, object]] = []
    for _, row in df.iterrows():
        norm_key = f"{normalize_admin_name(row.get('Country'))}|{normalize_admin_name(row.get('State'))}"
        match = states.get(norm_key)
        country = match["country_name"] if match else row.get("Country")
        state = match["department_name"] if match else row.get("State")
        state_key = match["state_key"] if match else f"{country}|{state}"
        records.append(
            {
                "state_key": state_key,
                "country_name": country,
                "department_name": state,
                "impact_country": row.get("Country"),
                "impact_state": row.get("State"),
                "impact_population": numeric_or_none(row.get("Population")),
                "impact_deaths": numeric_or_none(row.get("Deaths")),
                "deaths_per_capita": numeric_or_none(row.get("Deaths/Capita")),
                "impact_disappearances": numeric_or_none(row.get("Dissapereances")),
                "deaths_disappearances_per_capita": numeric_or_none(row.get("Death+Dissapearence/Capita")),
                "population_proxy": row.get("Population Year/Proxy"),
                "impact_source": row.get("Impact Source"),
                "population_source": row.get("Population Source"),
                "impact_notes": row.get("Notes"),
                "matched_dashboard_state": match is not None,
            }
        )
    return records


def rainfall_overlay() -> dict[str, object] | None:
    meta_path = WEB_DIR / "chirps_mitch_rainfall_overlay.json"
    png_path = WEB_DIR / "chirps_mitch_rainfall_overlay.png"
    if not meta_path.exists() or not png_path.exists():
        return None
    meta = read_json(meta_path)
    encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return {"data_uri": f"data:image/png;base64,{encoded}", "bounds_wgs84": meta["bounds_wgs84"]}


def lattice_offset(values: pd.Series, step: float) -> float:
    valid = pd.to_numeric(values, errors="coerce").dropna()
    if valid.empty:
        return 0.0
    offsets = ((valid / step).round(8) - (valid / step).round(8).apply(math.floor)) * step
    return round(float(offsets.mode().iloc[0]), 6)


def aligned_grid_values(min_coord: float, max_coord: float, step: float, offset: float) -> list[float]:
    start = math.floor((min_coord - step - offset) / step)
    end = math.ceil((max_coord + step - offset) / step)
    return [round(offset + idx * step, 6) for idx in range(start, end + 1)]


def country_grid_points(iso: str, country: str, lat_offset: float, lon_offset: float) -> list[dict[str, object]]:
    path = EXTERNAL_DIR / f"geoboundaries_adm1_{iso}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"Missing GeoBoundaries ADM1 file for Yang-Parag grid: {path}")
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    geom = gdf.geometry.union_all() if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    points: list[dict[str, object]] = []
    for lat in aligned_grid_values(min_lat, max_lat, YANG_GRID_STEP_DEGREES, lat_offset):
        for lon in aligned_grid_values(min_lon, max_lon, YANG_GRID_STEP_DEGREES, lon_offset):
            if geom.covers(Point(lon, lat)):
                points.append({"latitude": lat, "longitude": lon, "country": country, "country_iso": iso})
    return points


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    to_rad = math.pi / 180
    dlat = (lat2 - lat1) * to_rad
    dlon = (lon2 - lon1) * to_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin(dlon / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def yang_grid_metadata(records: list[dict[str, object]], lat_offset: float, lon_offset: float) -> dict[str, object]:
    lats = sorted({float(r["latitude"]) for r in records})
    lons = sorted({float(r["longitude"]) for r in records})
    lat_lattice_ok = all(abs(((lat - lat_offset) / YANG_GRID_STEP_DEGREES) - round((lat - lat_offset) / YANG_GRID_STEP_DEGREES)) < 1e-8 for lat in lats)
    lon_lattice_ok = all(abs(((lon - lon_offset) / YANG_GRID_STEP_DEGREES) - round((lon - lon_offset) / YANG_GRID_STEP_DEGREES)) < 1e-8 for lon in lons)
    lat_step_km = haversine_km(0, 0, YANG_GRID_STEP_DEGREES, 0)
    lon_km = [haversine_km(lat, 0, lat, YANG_GRID_STEP_DEGREES) for lat in lats]
    countries = sorted({country for r in records for country in str(r["country"]).split("; ")})
    return {
        "yang_parag_grid_countries": countries,
        "yang_parag_grid_step_degrees": YANG_GRID_STEP_DEGREES,
        "yang_parag_grid_lat_offset": lat_offset,
        "yang_parag_grid_lon_offset": lon_offset,
        "yang_parag_grid_lat_lattice_ok": lat_lattice_ok,
        "yang_parag_grid_lon_lattice_ok": lon_lattice_ok,
        "yang_parag_grid_lat_step_km": round(lat_step_km, 3),
        "yang_parag_grid_lon_step_km_min": round(min(lon_km), 3) if lon_km else None,
        "yang_parag_grid_lon_step_km_max": round(max(lon_km), 3) if lon_km else None,
        "yang_parag_grid_treated_points": int(sum(1 for r in records if r["is_original_treated"])),
        "yang_parag_grid_control_points": int(sum(1 for r in records if not r["is_original_treated"])),
    }


def read_yang_parag_source() -> pd.DataFrame:
    try:
        return pd.read_excel(YANG_PARAG_RAW)
    except ImportError:
        if not YANG_PARAG_GRID_CSV.exists():
            raise
        df = pd.read_csv(YANG_PARAG_GRID_CSV)
        if "source_country" in df.columns:
            source_country = df["source_country"].where(pd.notna(df["source_country"]), df.get("country"))
            df["country"] = source_country
        return df


def yang_parag_grid() -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    if not YANG_PARAG_RAW.exists():
        raise FileNotFoundError(f"Missing required Yang-Parag input: {YANG_PARAG_RAW}")
    df = read_yang_parag_source()
    required = {
        "latitude",
        "longitude",
        "grid_pop",
        "country",
        "total_country_pop",
        "pwind",
        "dist",
        "num_affecting",
        "month",
        "day",
        "hour",
        "name",
        "wspeed",
        "basin",
        "pradius34",
        "x_gjst",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Yang-Parag workbook is missing columns: {', '.join(missing)}")

    numeric_cols = [
        "latitude",
        "longitude",
        "grid_pop",
        "total_country_pop",
        "pwind",
        "dist",
        "num_affecting",
        "month",
        "day",
        "hour",
        "wspeed",
        "pradius34",
        "x_gjst",
    ]
    df = df.copy()
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)

    ca_source = df[df["country"].isin(CENTRAL_AMERICA_COUNTRY_SET)].copy()
    lat_offset = lattice_offset(ca_source["latitude"], YANG_GRID_STEP_DEGREES)
    lon_offset = lattice_offset(ca_source["longitude"], YANG_GRID_STEP_DEGREES)

    generated: dict[tuple[float, float], dict[str, object]] = {}
    for iso, country in CENTRAL_AMERICA_GRID_COUNTRIES.items():
        for point in country_grid_points(iso, country, lat_offset, lon_offset):
            key = (float(point["latitude"]), float(point["longitude"]))
            rec = generated.setdefault(key, {"latitude": key[0], "longitude": key[1], "countries": [], "country_isos": []})
            rec["countries"].append(point["country"])
            rec["country_isos"].append(point["country_iso"])

    source_by_key: dict[tuple[float, float], dict[str, object]] = {}
    for _, row in ca_source.iterrows():
        key = (round(float(row["latitude"]), 6), round(float(row["longitude"]), 6))
        row_dict = row.to_dict()
        current = source_by_key.get(key)
        row_x = float(row_dict["x_gjst"]) if pd.notna(row_dict.get("x_gjst")) else -1.0
        current_x = float(current["x_gjst"]) if current and pd.notna(current.get("x_gjst")) else -1.0
        if current is None or row_x > current_x:
            source_by_key[key] = row_dict

    x_values = [float(r["x_gjst"]) for r in source_by_key.values() if pd.notna(r.get("x_gjst")) and float(r["x_gjst"]) > 0]
    x_scale = float(pd.Series(x_values).quantile(0.95)) if x_values else 1.0
    if pd.isna(x_scale) or x_scale <= 0:
        x_scale = max(x_values) if x_values else 1.0

    half_step = 0.125
    records: list[dict[str, object]] = []
    for idx, key in enumerate(sorted(generated, key=lambda k: (min(generated[k]["countries"]), k[0], k[1])), start=1):
        base = generated[key]
        source = source_by_key.get(key, {})
        x_gjst = numeric_or_none(source.get("x_gjst")) or 0.0
        pwind = numeric_or_none(source.get("pwind"))
        is_original_treated = bool((pwind is not None and pwind > YANG_WIND_THRESHOLD_KT) or x_gjst > 0)
        source_name = source.get("name")
        source_has_exposure = bool(
            is_original_treated
            or pwind is not None
            or (source_name is not None and pd.notna(source_name) and str(source_name).strip())
        )
        country_names = sorted(set(base["countries"]))
        country_isos = sorted(set(base["country_isos"]))
        rec = {
            "grid_id": f"yp_{idx:04d}",
            "latitude": key[0],
            "longitude": key[1],
            "grid_step_degrees": YANG_GRID_STEP_DEGREES,
            "cell_south": key[0] - half_step,
            "cell_north": key[0] + half_step,
            "cell_west": key[1] - half_step,
            "cell_east": key[1] + half_step,
            "country": "; ".join(country_names),
            "country_iso": "; ".join(country_isos),
            "country_count": len(country_names),
            "source_country": source.get("country") if source_has_exposure else None,
            "grid_pop": numeric_or_none(source.get("grid_pop")),
            "total_country_pop": numeric_or_none(source.get("total_country_pop")),
            "pwind": pwind,
            "dist": numeric_or_none(source.get("dist")),
            "num_affecting": numeric_or_none(source.get("num_affecting")),
            "month": numeric_or_none(source.get("month")),
            "day": numeric_or_none(source.get("day")),
            "hour": numeric_or_none(source.get("hour")),
            "year": 1998,
            "name": source.get("name"),
            "wspeed": numeric_or_none(source.get("wspeed")),
            "basin": source.get("basin"),
            "pradius34": numeric_or_none(source.get("pradius34")),
            "x_gjst": x_gjst,
            "x_norm_robust": max(0.0, min(1.0, x_gjst / x_scale)),
            "wind_threshold_kt": YANG_WIND_THRESHOLD_KT,
            "is_original_treated": is_original_treated,
            "grid_class": "original_treated" if is_original_treated else "control",
        }
        records.append(rec)

    treated_points = [r for r in records if r["is_original_treated"]]
    for rec in records:
        if treated_points:
            rec["nearest_original_treated_grid_km"] = min(
                haversine_km(float(rec["latitude"]), float(rec["longitude"]), float(t["latitude"]), float(t["longitude"]))
                for t in treated_points
            )
        else:
            rec["nearest_original_treated_grid_km"] = None

    metadata = yang_grid_metadata(records, lat_offset, lon_offset)

    columns = [
        "grid_id",
        "latitude",
        "longitude",
        "grid_step_degrees",
        "cell_south",
        "cell_north",
        "cell_west",
        "cell_east",
        "country",
        "country_iso",
        "country_count",
        "source_country",
        "grid_pop",
        "total_country_pop",
        "pwind",
        "dist",
        "num_affecting",
        "month",
        "day",
        "hour",
        "year",
        "name",
        "wspeed",
        "basin",
        "pradius34",
        "x_gjst",
        "x_norm_robust",
        "wind_threshold_kt",
        "is_original_treated",
        "grid_class",
        "nearest_original_treated_grid_km",
    ]
    out_df = pd.DataFrame(records, columns=columns).astype(object).where(pd.notna(pd.DataFrame(records, columns=columns)), None)
    records = out_df.to_dict(orient="records")
    geojson = {
        "type": "FeatureCollection",
        "name": "yang_parag_mitch_grid",
        "features": [
            {
                "type": "Feature",
                "properties": {k: v for k, v in row.items() if k not in {"latitude", "longitude"}},
                "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
            }
            for row in records
        ],
    }
    output_path(YANG_PARAG_GRID_CSV).write_text(out_df.to_csv(index=False), encoding="utf-8")
    output_path(YANG_PARAG_GRID_GEOJSON).write_text(safe_json(geojson), encoding="utf-8")
    return records, geojson, metadata


def ntl_records(matched_meta: dict[str, dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, int]]:
    if not NTL_RAW.exists():
        raise FileNotFoundError(f"Missing required NTL input: {NTL_RAW}")
    usecols = [
        "satellite",
        "ADM0_CODE",
        "ADM1_CODE",
        "ADM2_CODE",
        "year",
        "stable_sum",
        "stable_count",
    ]
    raw = pd.read_csv(NTL_RAW, usecols=usecols, low_memory=False)
    raw["muni_key"] = (
        raw["ADM0_CODE"].astype("Int64").astype(str)
        + "_"
        + raw["ADM1_CODE"].astype("Int64").astype(str)
        + "_"
        + raw["ADM2_CODE"].astype("Int64").astype(str)
    )
    raw_units = int(raw["muni_key"].nunique())
    raw = raw[raw["muni_key"].isin(matched_meta)].copy()
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce").astype("Int64")
    raw["stable_sum"] = pd.to_numeric(raw["stable_sum"], errors="coerce")
    raw["stable_count"] = pd.to_numeric(raw["stable_count"], errors="coerce")
    raw = raw.dropna(subset=["year", "stable_sum"])
    raw["country_name"] = raw["muni_key"].map(lambda k: matched_meta[k]["country_name"])
    raw["department_name"] = raw["muni_key"].map(lambda k: matched_meta[k]["department_name"])
    raw["municipality_name"] = raw["muni_key"].map(lambda k: matched_meta[k]["municipality_name"])
    keep = [
        "muni_key",
        "satellite",
        "country_name",
        "department_name",
        "municipality_name",
        "year",
        "stable_sum",
        "stable_count",
    ]
    return raw[keep].to_dict(orient="records"), {
        "raw_ntl_municipalities": raw_units,
        "matched_ntl_municipalities": int(raw["muni_key"].nunique()),
        "unmatched_ntl_municipalities": raw_units - int(raw["muni_key"].nunique()),
        "raw_ntl_rows": int(len(pd.read_csv(NTL_RAW, usecols=["year"]))),
        "matched_ntl_rows": int(len(raw)),
    }


def html_template() -> str:
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mitch Integrated NTL, Exposure, and Results Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {
  --ink: #17202a;
  --muted: #667085;
  --line: #dce3ec;
  --page: #f5f7fb;
  --panel: #ffffff;
  --accent: #0f766e;
  --treat: #b91c1c;
  --blue: #2563eb;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--page);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  letter-spacing: 0;
}
button, select, input { font: inherit; }
header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 22px 14px;
  background: #fff;
  border-bottom: 1px solid var(--line);
}
h1 { margin: 0; font-size: 23px; }
.sub { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
.coverage {
  max-width: 430px;
  padding: 9px 11px;
  border: 1px solid #c7e7e2;
  border-radius: 8px;
  background: #f0fbf9;
  color: #164e49;
  font-size: 12px;
  line-height: 1.35;
}
.global-controls, .exposure-controls, .results-controls {
  display: grid;
  grid-template-columns: repeat(6, minmax(145px, 1fr));
  gap: 10px;
  padding: 12px 18px;
  background: #fff;
  border-bottom: 1px solid var(--line);
}
.control { min-width: 0; }
label, .label {
  display: block;
  margin-bottom: 4px;
  color: #374456;
  font-size: 11px;
  font-weight: 740;
  text-transform: uppercase;
}
select, input[type="range"], input[type="search"] { width: 100%; }
select, input[type="search"] {
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
}
select { min-height: 34px; padding: 6px; }
select[multiple] { height: 94px; }
input[type="search"] { height: 34px; padding: 0 9px; }
.range-value, .tiny { margin-top: 4px; color: var(--muted); font-size: 12px; }
.sat-box { display: flex; flex-wrap: wrap; gap: 6px; }
.check-panel {
  min-height: 104px;
  max-height: 146px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
  padding: 6px;
}
.check-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 2px 3px;
  color: #2d3748;
  font-size: 12px;
  text-transform: none;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fbfcfe;
  padding: 0 8px;
  color: #2d3748;
  font-size: 12px;
}
.mini {
  min-height: 30px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #f8fafc;
  padding: 0 9px;
  cursor: pointer;
  font-size: 12px;
}
.tabs {
  display: flex;
  gap: 8px;
  padding: 10px 18px 0;
  background: #fff;
}
.tabs button {
  border: 1px solid var(--line);
  border-bottom: 0;
  border-radius: 8px 8px 0 0;
  background: #f8fafc;
  padding: 10px 15px;
  cursor: pointer;
  font-weight: 720;
}
.tabs button.active { background: var(--page); color: var(--accent); border-color: #b8dcd7; }
.tab { display: none; padding: 16px 18px 24px; }
.tab.active { display: block; }
.grid-2 {
  display: grid;
  grid-template-columns: minmax(420px, 1.15fr) minmax(360px, .85fr);
  gap: 14px;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.panel.pad { padding: 13px; }
.panel h2, .panel h3 {
  margin: 0;
  padding: 12px 14px 4px;
  font-size: 16px;
}
.panel .note {
  margin: 0;
  padding: 0 14px 10px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}
.map {
  height: 520px;
  min-height: 420px;
}
.chart { min-height: 360px; }
.short-chart { min-height: 285px; }
.year-tools {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 12px;
  margin: 8px 0 12px;
}
.year-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(44px, 1fr));
  gap: 5px;
}
.year-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 28px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fbfcfe;
  color: #334155;
  font-size: 11px;
  text-transform: none;
}
.year-box.transition { border-color: #f2c27b; background: #fff8eb; }
.year-note {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.chart-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1fr);
  gap: 14px;
}
.chart-cell {
  min-height: 430px;
  border: 1px solid #eef2f6;
  border-radius: 8px;
  background: #fff;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.metric {
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  background: #fbfcfe;
  padding: 9px;
}
.metric span { display: block; color: var(--muted); font-size: 11px; }
.metric b { display: block; margin-top: 3px; font-size: 17px; }
.table-wrap { max-height: 430px; overflow: auto; border-top: 1px solid var(--line); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 7px 8px; border-bottom: 1px solid #eef2f6; text-align: left; white-space: nowrap; }
th { position: sticky; top: 0; background: #f8fafc; z-index: 1; color: #344054; }
tr.primary { background: #fff7ed; font-weight: 760; }
.eq {
  margin: 0 0 10px;
  padding: 10px 12px;
  border: 1px solid #d7e7ff;
  border-radius: 8px;
  background: #f5f9ff;
  color: #1d4f8f;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
}
.warn {
  margin: 0 0 10px;
  padding: 9px 11px;
  border: 1px solid #f2c27b;
  border-radius: 8px;
  background: #fff8eb;
  color: #7a4300;
  font-size: 12px;
  line-height: 1.35;
}
.interpretation {
  margin: 10px 12px 13px;
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
}
.legend {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: #17202a;
  font-size: 12px;
  line-height: 1.35;
}
.legend-bar {
  width: 170px;
  height: 10px;
  margin: 6px 0;
  background: linear-gradient(90deg, #b91c1c, #f2c94c, #2f9e44);
}
.legend-bar.blue {
  background: linear-gradient(90deg, #dbeafe, #60a5fa, #1d4ed8);
}
.mode-yang { display: none; }
body.yang-mode .mode-yang { display: block; }
.not-yang { display: block; }
body.yang-mode .not-yang { display: none; }
@media (max-width: 1120px) {
  header, .grid-2 { display: block; }
  .coverage { margin-top: 10px; max-width: none; }
  .global-controls, .exposure-controls, .results-controls { grid-template-columns: repeat(2, minmax(145px, 1fr)); }
  .panel { margin-bottom: 14px; }
  .year-tools { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .global-controls, .exposure-controls, .results-controls { grid-template-columns: 1fr; }
  .chart-cell { min-height: 360px; }
  .map { height: 440px; }
}
</style>
</head>
<body>
<header>
  <div>
    <h1>Hurricane Mitch Integrated Dashboard</h1>
    <p class="sub">Nighttime lights, Best Track, CHIRPS rainfall, and statistically separated results in one static window.</p>
  </div>
  <div class="coverage" id="coverageNote"></div>
</header>

<section class="global-controls" aria-label="Shared NTL and geography controls">
  <div class="control">
    <span class="label">Satellites</span>
    <div id="satBox" class="sat-box"></div>
    <label class="chip" style="margin-top:6px;"><input id="deaggregateSats" type="checkbox"> Show satellite-specific lines</label>
  </div>
  <div class="control">
    <label for="countrySearch">Countries</label>
    <input id="countrySearch" type="search" placeholder="Search countries">
    <div id="countryBox" class="check-panel"></div>
    <div class="tiny"><button class="mini" id="allCountries" type="button">All countries</button></div>
  </div>
  <div class="control">
    <label for="stateSearch">States / Departments</label>
    <input id="stateSearch" type="search" placeholder="Search states">
    <div id="stateBox" class="check-panel"></div>
    <div class="tiny"><button class="mini" id="clearStates" type="button">All shown states</button> No boxes checked means all shown.</div>
  </div>
  <div class="control">
    <label for="muniSearch">Municipalities</label>
    <input id="muniSearch" type="search" placeholder="Filter municipality names">
    <div id="muniBox" class="check-panel"></div>
    <div class="tiny"><button class="mini" id="clearMunis" type="button">All shown municipalities</button> No boxes checked means all shown.</div>
  </div>
  <div class="control">
    <label for="preFilter">Pre-Mitch NTL Filter</label>
    <input id="preFilter" type="range" min="0" max="1000" step="0.1" value="70.7">
    <div class="range-value">1992-1997 mean >= <span id="preFilterValue">100</span></div>
    <div class="tiny">Nonlinear scale for finer low-end control.</div>
  </div>
  <div class="control">
    <span class="label">Sample</span>
    <div id="sampleSummary" class="range-value"></div>
  </div>
</section>

<nav class="tabs" aria-label="Dashboard tabs">
  <button type="button" class="active" data-tab="ntlTab">Dependent</button>
  <button type="button" data-tab="exposureTab">Independent</button>
  <button type="button" data-tab="resultsTab">Results</button>
</nav>

<section id="ntlTab" class="tab active">
  <div class="grid-2">
    <section class="panel">
      <h2>NTL Municipality Map</h2>
      <p class="note">Selected municipalities are highlighted; municipalities below the pre-mean threshold are blacked out and excluded from analysis.</p>
      <div id="ntlMap" class="map"></div>
    </section>
    <section class="panel pad">
      <div class="metrics" id="ntlMetrics"></div>
      <h3 style="padding:0 0 6px;">Year Comparison</h3>
      <div class="year-tools">
        <div>
          <span class="label">Baseline years</span>
          <div id="baselineYears" class="year-grid"></div>
        </div>
        <div>
          <span class="label">Comparison years</span>
          <div id="comparisonYears" class="year-grid"></div>
        </div>
      </div>
      <p id="yearComparisonSummary" class="year-note"></p>
      <p class="year-note">Dashed markers are drawn at 1998 and 1999; 1998 is the Mitch transition/impact year.</p>
    </section>
  </div>
  <section class="panel" style="margin-top:14px;">
    <h2>NTL Ranking</h2>
    <p class="note">Selected-satellite municipality-year values are collapsed to means before metrics are computed.</p>
    <div class="table-wrap"><table id="ntlRankTable"></table></div>
  </section>
  <section class="panel" style="margin-top:14px;">
    <h2>NTL Graphs</h2>
    <p class="note">Each geography-level NTL sum is followed by its log1p version. The satellite-specific toggle applies only to charts with 20 or fewer plotted geography units.</p>
    <div id="ntlGraphGrid" class="chart-grid" style="padding:10px;"></div>
  </section>
</section>

<section id="exposureTab" class="tab">
  <section class="exposure-controls" aria-label="Exposure controls">
    <div class="control">
      <label for="riskMode">Risk Mode</label>
      <select id="riskMode">
        <option value="best">Best Track</option>
        <option value="rain">CHIRPS</option>
        <option value="death">Deaths per capita</option>
        <option value="yang_parag">Yang-Parag</option>
        <option value="weighted">Weighted</option>
      </select>
    </div>
    <div class="control not-yang">
      <label for="windThreshold">Wind Threshold (Best Track)</label>
      <select id="windThreshold">
        <option value="34">34 kt tropical storm</option>
        <option value="50">50 kt storm</option>
        <option value="64" selected>64 kt hurricane</option>
        <option value="83">83 kt Cat 2</option>
        <option value="96">96 kt Cat 3</option>
        <option value="113">113 kt Cat 4</option>
        <option value="137">137 kt Cat 5</option>
      </select>
    </div>
    <div class="control not-yang">
      <label for="distanceRadius">Distance Radius (Best Track)</label>
      <input id="distanceRadius" type="range" min="0" max="500" step="5" value="150">
      <div class="range-value"><span id="distanceRadiusValue">150</span> km</div>
    </div>
    <div class="control not-yang">
      <label for="rainMetric">Rainfall Metric (CHIRPS)</label>
      <select id="rainMetric">
        <option value="rain_max_daily_mean_mm">Max daily rainfall</option>
        <option value="rain_max_daily_anomaly_mm">Max daily anomaly</option>
        <option value="rain_total_mean_mm" selected>Total rainfall</option>
        <option value="rain_total_anomaly_mm">Total anomaly</option>
      </select>
    </div>
    <div class="control not-yang">
      <label for="riskWeight">Wind Weight (Weighted; uses Best Track)</label>
      <input id="riskWeight" type="range" min="0" max="1" step="0.05" value="0.50">
      <div class="range-value"><span id="riskWeightValue">0.50</span></div>
    </div>
    <div class="control not-yang">
      <label for="deathWeight">Death Weight (Weighted)</label>
      <input id="deathWeight" type="range" min="0" max="1" step="0.05" value="0.00">
      <div class="range-value"><span id="deathWeightValue">0.00</span></div>
    </div>
    <div class="control not-yang">
      <label for="treatmentCutoff">Treatment Cutoff (score modes)</label>
      <input id="treatmentCutoff" type="range" min="0" max="1" step="0.01" value="0.50">
      <div class="range-value">score >= <span id="treatmentCutoffValue">0.50</span></div>
      <label class="chip" style="margin-top:6px;"><input id="scaleWind" type="checkbox" checked> Scale wind</label>
    </div>
    <div class="control mode-yang">
      <span class="label">Yang-Parag Expansion</span>
      <label class="chip"><input id="yangExpand" type="checkbox"> Expand treated grid</label>
      <input id="yangExpandRadius" type="range" min="0" max="250" step="5" value="0">
      <div class="range-value">gray grid points within <span id="yangExpandRadiusValue">0</span> km become blue</div>
    </div>
  </section>
  <div class="grid-2">
    <section class="panel">
      <h2>Exposure And Binary Treatment Map</h2>
      <p class="note">Treatment is binary and comes only from the selected exposure score cutoff. Excluded municipalities are blacked out.</p>
      <div id="exposureMap" class="map"></div>
    </section>
    <section class="panel pad">
      <div class="metrics" id="exposureMetrics"></div>
      <div id="riskDistribution" class="short-chart"></div>
      <div id="trackPlot" class="short-chart"></div>
    </section>
  </div>
  <section class="panel" style="margin-top:14px;">
    <h2>Independent Variable Detail</h2>
    <div class="table-wrap"><table id="exposureTable"></table></div>
  </section>
</section>

<section id="resultsTab" class="tab">
  <section class="results-controls" aria-label="Regression controls">
    <div class="control">
      <span class="label">Fixed Effects</span>
      <label class="chip"><input id="muniFE" type="checkbox" checked> Unit FE</label>
      <label class="chip"><input id="yearFE" type="checkbox"> Year FE</label>
      <label class="chip"><input id="countryFE" type="checkbox"> Country FE</label>
    </div>
    <div class="control">
      <span class="label">Primary Outcome</span>
      <div class="range-value">1999 treated-year interactions on log1p(NTL) and raw NTL, omitted base 1997.</div>
    </div>
    <div class="control">
      <span class="label">Model Scope</span>
      <div class="range-value">Regional sample only; no Honduras-only specification.</div>
    </div>
    <div class="control">
      <span class="label">Stars</span>
      <div class="range-value">* 90%, ** 95%, *** 99% using conventional SEs.</div>
    </div>
    <div class="control" style="grid-column: span 2;">
      <span class="label">Specification Answer</span>
      <div id="specAnswer" class="range-value"></div>
    </div>
  </section>
  <div class="grid-2">
    <section class="panel pad">
      <p id="equationText" class="eq"></p>
      <p class="warn">Regression standard errors are conventional and not clustered yet. The mean graphs residualize the selected outcome by the checked fixed effects before plotting; with no fixed effects selected, they reduce to raw group means.</p>
      <div id="didMeansPlot" class="chart"></div>
    </section>
    <section class="panel pad">
      <div class="metrics" id="resultMetrics"></div>
      <div id="eventStudyPlot" class="chart"></div>
    </section>
  </div>
  <section class="panel" style="margin-top:14px;">
    <h2>Logged Regression Table</h2>
    <div class="table-wrap"><table id="regressionTable"></table></div>
    <p id="regressionInterpretationLog" class="interpretation"></p>
  </section>
  <div class="grid-2" style="margin-top:14px;">
    <section class="panel pad">
      <div id="didMeansRawPlot" class="chart"></div>
    </section>
    <section class="panel pad">
      <div id="eventStudyRawPlot" class="chart"></div>
    </section>
  </div>
  <section class="panel" style="margin-top:14px;">
    <h2>Raw NTL Regression Table</h2>
    <div class="table-wrap"><table id="regressionTableRaw"></table></div>
    <p id="regressionInterpretationRaw" class="interpretation"></p>
  </section>
</section>

<script>
const MUNICIPALITIES = __MUNICIPALITIES__;
const STATE_IMPACTS = __STATE_IMPACTS__;
const NTL_RAW = __NTL_RAW__;
const TRACK_LINE = __TRACK_LINE__;
const TRACK_POINTS = __TRACK_POINTS__;
const TRACK_ROWS = __TRACK_ROWS__;
const SWATHS = __SWATHS__;
const RAIN_OVERLAY = __RAIN_OVERLAY__;
const YANG_PARAG_GRID = __YANG_PARAG_GRID__;
const MANIFEST = __MANIFEST__;

const YEARS = Array.from({ length: 22 }, (_, i) => 1992 + i);
const PRE_YEARS = YEARS.filter(y => y <= 1997);
const POST_YEARS = YEARS.filter(y => y >= 1999);
const REF_YEAR = 1997;
const PRIMARY_YEAR = 1999;
const IMPACT_YEARS = [1998, 1999];
const TREATED_COLOR = '#b91c1c';
const CONTROL_COLOR = '#15803d';
const YANG_GRID_TREATED_COLOR = TREATED_COLOR;
const YANG_GRID_EXPANDED_COLOR = '#2563eb';
const YANG_MUNI_EXPANDED_COLOR = '#eab308';
const YANG_CONTROL_COLOR = '#9ca3af';
const COUNTERFACTUAL_COLOR = '#475569';
const PRE_FILTER_MAX = 20000;
const DEFAULT_CUTOFF_BY_RISK = { best: '0.50', rain: '0.50', death: '0.05', yang_parag: '0.00', weighted: '0.50' };
const DEFAULT_OFF_COUNTRIES = new Set(['Costa Rica', 'Panama']);
const featureByMuni = new Map(MUNICIPALITIES.features.map(f => [f.properties.muni_key, f]));
const impactByState = new Map(STATE_IMPACTS.filter(r => r.matched_dashboard_state).map(r => [r.state_key, r]));
const countries = [...new Set(MUNICIPALITIES.features.map(f => f.properties.country_name))].sort();
const states = [...new Map(MUNICIPALITIES.features.map(f => {
  const p = f.properties;
  return [`${p.country_name}|${p.department_name}`, { key: `${p.country_name}|${p.department_name}`, country_name: p.country_name, department_name: p.department_name }];
})).values()].sort((a, b) => a.country_name.localeCompare(b.country_name) || a.department_name.localeCompare(b.department_name));
const satellites = [...new Set(NTL_RAW.map(r => r.satellite))].sort();
let active = new Map();
let activeState = new Map();
let collapsed = { rows: [], byMuni: new Map(), preMean: new Map(), stateRows: [], byState: new Map(), statePreMean: new Map() };
let selectedCountries = new Set(countries.filter(c => !DEFAULT_OFF_COUNTRIES.has(c)));
let selectedStates = new Set();
let selectedMunis = new Set();
let ntlMap = null;
let exposureMap = null;
let ntlMuniLayer = null;
let exposureMuniLayer = null;
let ntlRainLayer = null;
let exposureRainLayer = null;
let yangParagLayer = null;
const YANG_X_VALUES = YANG_PARAG_GRID.map(r => num(r.x_gjst)).filter(v => v !== null && v > 0);
const YANG_X_MAX = YANG_X_VALUES.length ? Math.max(...YANG_X_VALUES) : 0;
const YANG_X_SCALE = quantile(YANG_X_VALUES, 0.95) || YANG_X_MAX || 1;
const yangDistanceCache = new Map();

const controls = {
  satBox: document.getElementById('satBox'),
  deaggregateSats: document.getElementById('deaggregateSats'),
  countrySearch: document.getElementById('countrySearch'),
  countryBox: document.getElementById('countryBox'),
  stateSearch: document.getElementById('stateSearch'),
  stateBox: document.getElementById('stateBox'),
  muniSearch: document.getElementById('muniSearch'),
  muniBox: document.getElementById('muniBox'),
  allCountries: document.getElementById('allCountries'),
  clearStates: document.getElementById('clearStates'),
  clearMunis: document.getElementById('clearMunis'),
  baselineYears: document.getElementById('baselineYears'),
  comparisonYears: document.getElementById('comparisonYears'),
  preFilter: document.getElementById('preFilter'),
  riskMode: document.getElementById('riskMode'),
  windThreshold: document.getElementById('windThreshold'),
  distanceRadius: document.getElementById('distanceRadius'),
  rainMetric: document.getElementById('rainMetric'),
  riskWeight: document.getElementById('riskWeight'),
  deathWeight: document.getElementById('deathWeight'),
  treatmentCutoff: document.getElementById('treatmentCutoff'),
  yangExpand: document.getElementById('yangExpand'),
  yangExpandRadius: document.getElementById('yangExpandRadius'),
  scaleWind: document.getElementById('scaleWind'),
  muniFE: document.getElementById('muniFE'),
  yearFE: document.getElementById('yearFE'),
  countryFE: document.getElementById('countryFE')
};

function num(value) {
  const out = Number(value);
  return Number.isFinite(out) ? out : null;
}
function clamp(x, lo = 0, hi = 1) { return Math.max(lo, Math.min(hi, x)); }
function quantile(values, q) {
  const vals = values.filter(v => v !== null && Number.isFinite(v)).slice().sort((a, b) => a - b);
  if (!vals.length) return null;
  const pos = (vals.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return vals[lo];
  return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo);
}
function fmt(value, digits = 2) {
  const n = num(value);
  if (n === null) return 'NA';
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}
function fmtInt(value) { return fmt(value, 0); }
function fmtPct(value) {
  const n = num(value);
  return n === null ? 'NA' : `${n.toFixed(1)}%`;
}
function preFilterThreshold() {
  const t = clamp(Number(controls.preFilter.value) / 1000);
  return Math.round(PRE_FILTER_MAX * t * t);
}
function impactYearShapes() {
  return IMPACT_YEARS.map(year => ({
    type: 'line',
    x0: year,
    x1: year,
    y0: 0,
    y1: 1,
    yref: 'paper',
    line: { color: '#111827', dash: 'dash', width: 1 }
  }));
}
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}
function checkedValues(box) {
  return [...box.querySelectorAll('input[type=checkbox]')].filter(x => x.checked).map(x => x.value);
}
function renderCheckList(box, options, selected, onChange) {
  box.innerHTML = '';
  const selectedSet = new Set(selected || []);
  for (const opt of options) {
    const label = document.createElement('label');
    label.className = 'check-row';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = opt.value;
    input.checked = selectedSet.has(opt.value);
    input.addEventListener('change', onChange);
    label.append(input, document.createTextNode(opt.label));
    box.appendChild(label);
  }
  if (!options.length) box.innerHTML = '<div class="tiny">No matches.</div>';
}
function stateKey(props) {
  return `${props.country_name}|${props.department_name}`;
}
function selectedCountrySet() {
  return selectedCountries.size ? new Set(selectedCountries) : new Set(countries);
}
function selectedStateSet() {
  return selectedStates.size ? new Set(selectedStates) : null;
}
function selectedMuniSet() {
  return selectedMunis.size ? new Set(selectedMunis) : null;
}
function selectedBaselineYears() {
  return checkedValues(controls.baselineYears).map(Number).sort((a, b) => a - b);
}
function selectedComparisonYears() {
  return checkedValues(controls.comparisonYears).map(Number).sort((a, b) => a - b);
}
function isGeoSelected(props) {
  const countrySet = selectedCountrySet();
  const stateSet = selectedStateSet();
  const muniSet = selectedMuniSet();
  if (!countrySet.has(props.country_name)) return false;
  if (stateSet && !stateSet.has(stateKey(props))) return false;
  if (muniSet && !muniSet.has(props.muni_key)) return false;
  return true;
}
function muniName(props) {
  return props.municipality_name || props.ADM2_NAME || props.muni_key;
}
function colorRamp(t, stops) {
  const x = clamp(t) * (stops.length - 1);
  const i = Math.floor(x);
  const frac = x - i;
  const a = stops[i], b = stops[Math.min(i + 1, stops.length - 1)];
  const rgb = a.map((v, j) => Math.round(v + frac * (b[j] - v)));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}
function ntlChangeColor(change) {
  if (!change || change.category === 'insufficient') return '#cbd5e1';
  if (change.category === 'loss') return colorRamp(clamp(Math.abs(change.anchorPct || 0) / 60), [[254,226,226], [248,113,113], [185,28,28]]);
  if (change.category === 'slowdown') return colorRamp(clamp(Math.abs(change.trendPct || 0) / 35), [[254,249,195], [250,204,21], [180,83,9]]);
  return colorRamp(clamp(Math.max(0, change.trendPct || change.anchorPct || 0) / 35), [[220,252,231], [74,222,128], [22,101,52]]);
}
function blueRamp(score) {
  return colorRamp(clamp(score ?? 0), [[219,234,254], [96,165,250], [29,78,216]]);
}

function initControls() {
  satellites.forEach(sat => {
    const label = document.createElement('label');
    label.className = 'chip';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = sat;
    input.checked = true;
    input.addEventListener('change', () => {
      const checked = [...controls.satBox.querySelectorAll('input[type=checkbox]')].filter(x => x.checked);
      if (!checked.length) input.checked = true;
      updateAll();
    });
    label.append(input, document.createTextNode(sat));
    controls.satBox.appendChild(label);
  });
  renderCountryOptions(countries);
  renderStateOptions();
  renderMuniOptions();
  renderYearBoxes();
  controls.deaggregateSats.addEventListener('change', updateAll);
  controls.countrySearch.addEventListener('input', () => renderCountryOptions());
  controls.stateSearch.addEventListener('input', renderStateOptions);
  controls.muniSearch.addEventListener('input', renderMuniOptions);
  controls.allCountries.addEventListener('click', () => { selectedCountries = new Set(countries); renderCountryOptions(); renderStateOptions(); renderMuniOptions(); updateAll(); });
  controls.clearStates.addEventListener('click', () => { selectedStates.clear(); renderStateOptions(); renderMuniOptions(); updateAll(); });
  controls.clearMunis.addEventListener('click', () => { selectedMunis.clear(); renderMuniOptions(); updateAll(); });
  controls.riskMode.addEventListener('input', () => { applyRiskModeDefault(); updateAll(); });
  controls.riskMode.addEventListener('change', () => { applyRiskModeDefault(); updateAll(); });
  for (const el of [controls.preFilter, controls.windThreshold, controls.distanceRadius, controls.rainMetric, controls.riskWeight, controls.deathWeight, controls.treatmentCutoff, controls.yangExpand, controls.yangExpandRadius, controls.scaleWind]) {
    el.addEventListener('input', updateAll);
    el.addEventListener('change', updateAll);
  }
  for (const el of [controls.muniFE, controls.yearFE, controls.countryFE]) {
    el.addEventListener('change', () => { enforceFERules(); updateAll(); });
  }
  document.querySelectorAll('.tabs button').forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });
}

function renderCountryOptions() {
  const q = controls.countrySearch.value.trim().toLowerCase();
  const opts = countries
    .filter(c => !q || c.toLowerCase().includes(q))
    .map(c => ({ value: c, label: c }));
  renderCheckList(controls.countryBox, opts, [...selectedCountries], event => {
    if (event.target.checked) selectedCountries.add(event.target.value);
    else selectedCountries.delete(event.target.value);
    if (!selectedCountries.size) {
      selectedCountries = new Set(countries);
      renderCountryOptions();
    }
    renderStateOptions();
    renderMuniOptions();
    updateAll();
  });
}
function renderStateOptions() {
  const countrySet = selectedCountrySet();
  const q = controls.stateSearch.value.trim().toLowerCase();
  const opts = states
    .filter(s => countrySet.has(s.country_name))
    .filter(s => !q || `${s.department_name} ${s.country_name}`.toLowerCase().includes(q))
    .map(s => ({ value: s.key, label: `${s.department_name} - ${s.country_name}` }));
  const valid = new Set(opts.map(o => o.value));
  selectedStates = new Set([...selectedStates].filter(v => valid.has(v)));
  renderCheckList(controls.stateBox, opts, [...selectedStates], event => {
    if (event.target.checked) selectedStates.add(event.target.value);
    else selectedStates.delete(event.target.value);
    renderMuniOptions();
    updateAll();
  });
}
function renderMuniOptions() {
  const countrySet = selectedCountrySet();
  const stateSet = selectedStateSet();
  const q = controls.muniSearch.value.trim().toLowerCase();
  const opts = MUNICIPALITIES.features
    .map(f => f.properties)
    .filter(p => countrySet.has(p.country_name))
    .filter(p => !stateSet || stateSet.has(stateKey(p)))
    .filter(p => !q || `${p.municipality_name} ${p.department_name} ${p.country_name}`.toLowerCase().includes(q))
    .sort((a, b) => a.country_name.localeCompare(b.country_name) || a.department_name.localeCompare(b.department_name) || a.municipality_name.localeCompare(b.municipality_name))
    .map(p => ({ value: p.muni_key, label: `${p.municipality_name} - ${p.department_name}, ${p.country_name}` }));
  const valid = new Set(opts.map(o => o.value));
  selectedMunis = new Set([...selectedMunis].filter(v => valid.has(v)));
  renderCheckList(controls.muniBox, opts, [...selectedMunis], event => {
    if (event.target.checked) selectedMunis.add(event.target.value);
    else selectedMunis.delete(event.target.value);
    updateAll();
  });
}

function applyRiskModeDefault() {
  controls.treatmentCutoff.value = DEFAULT_CUTOFF_BY_RISK[controls.riskMode.value] || '0.50';
}
function updateModeControls() {
  document.body.classList.toggle('yang-mode', controls.riskMode.value === 'yang_parag');
}
function renderYearBoxes() {
  const make = (box, selected) => {
    box.innerHTML = '';
    YEARS.forEach(year => {
      const label = document.createElement('label');
      label.className = `year-box${year === 1998 ? ' transition' : ''}`;
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = year;
      input.checked = selected.includes(year);
      input.addEventListener('change', () => {
        ensureYearSelection();
        updateAll();
      });
      label.append(input, document.createTextNode(String(year)));
      box.appendChild(label);
    });
  };
  make(controls.baselineYears, PRE_YEARS);
  make(controls.comparisonYears, [PRIMARY_YEAR]);
}
function ensureYearSelection() {
  if (!checkedValues(controls.baselineYears).length) {
    const fallback = controls.baselineYears.querySelector(`input[value="${REF_YEAR}"]`);
    if (fallback) fallback.checked = true;
  }
  if (!checkedValues(controls.comparisonYears).length) {
    const fallback = controls.comparisonYears.querySelector(`input[value="${PRIMARY_YEAR}"]`);
    if (fallback) fallback.checked = true;
  }
}

function activateTab(id) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === id));
  if (id === 'ntlTab') refreshMap(ntlMap, ntlMuniLayer);
  if (id === 'exposureTab') refreshMap(exposureMap, exposureMuniLayer);
}
function refreshMap(map, layer) {
  if (!map) return;
  [40, 180, 520].forEach(delay => setTimeout(() => {
    map.invalidateSize();
    if (layer && layer.getBounds && layer.getBounds().isValid()) map.fitBounds(layer.getBounds(), { padding: [18, 18] });
  }, delay));
}

function activeSatSet() {
  return new Set([...controls.satBox.querySelectorAll('input[type=checkbox]')].filter(x => x.checked).map(x => x.value));
}

function collapsePanel() {
  const satSet = activeSatSet();
  const countrySet = selectedCountrySet();
  const stateSet = selectedStateSet();
  const muniSet = selectedMuniSet();
  const acc = new Map();
  for (const r of NTL_RAW) {
    if (!satSet.has(r.satellite)) continue;
    if (!countrySet.has(r.country_name)) continue;
    if (stateSet && !stateSet.has(stateKey(r))) continue;
    if (muniSet && !muniSet.has(r.muni_key)) continue;
    const key = `${r.muni_key}|${r.year}`;
    const rec = acc.get(key) || { muni_key: r.muni_key, year: Number(r.year), country_name: r.country_name, department_name: r.department_name, municipality_name: r.municipality_name, sum: 0, n: 0 };
    const y = num(r.stable_sum);
    if (y === null) continue;
    rec.sum += y;
    rec.n += 1;
    acc.set(key, rec);
  }
  const rows = [...acc.values()].map(r => {
    const stable = r.sum / r.n;
    return { muni_key: r.muni_key, year: r.year, country_name: r.country_name, department_name: r.department_name, municipality_name: r.municipality_name, stable_sum: stable, log_ntl: Math.log1p(Math.max(0, stable)) };
  });
  const byMuni = new Map();
  for (const r of rows) {
    if (!byMuni.has(r.muni_key)) byMuni.set(r.muni_key, []);
    byMuni.get(r.muni_key).push(r);
  }
  for (const arr of byMuni.values()) arr.sort((a, b) => a.year - b.year);
  const preMean = new Map();
  for (const [muni, arr] of byMuni.entries()) {
    const vals = arr.filter(r => r.year <= REF_YEAR).map(r => r.stable_sum);
    if (vals.length) preMean.set(muni, vals.reduce((a, b) => a + b, 0) / vals.length);
  }
  const stateAcc = new Map();
  for (const r of rows) {
    const sKey = stateKey(r);
    const key = `${sKey}|${r.year}`;
    const rec = stateAcc.get(key) || { state_key: sKey, year: r.year, country_name: r.country_name, department_name: r.department_name, stable_sum: 0 };
    rec.stable_sum += r.stable_sum;
    stateAcc.set(key, rec);
  }
  const stateRows = [...stateAcc.values()].map(r => ({ ...r, log_ntl: Math.log1p(Math.max(0, r.stable_sum)) }));
  const byState = new Map();
  for (const r of stateRows) {
    if (!byState.has(r.state_key)) byState.set(r.state_key, []);
    byState.get(r.state_key).push(r);
  }
  for (const arr of byState.values()) arr.sort((a, b) => a.year - b.year);
  const statePreMean = new Map();
  for (const [key, arr] of byState.entries()) {
    const vals = arr.filter(r => r.year <= REF_YEAR).map(r => r.stable_sum);
    if (vals.length) statePreMean.set(key, vals.reduce((a, b) => a + b, 0) / vals.length);
  }
  return { rows, byMuni, preMean, stateRows, byState, statePreMean };
}

function selectedBucket(radius) {
  if (radius <= 75) return 50;
  if (radius <= 125) return 100;
  if (radius <= 175) return 150;
  return 200;
}
function swathScore(props, threshold, scaled) {
  if (threshold <= 34) return scaled ? num(props.share_area_r34) || 0 : (num(props.any_r34) ? 1 : 0);
  if (threshold <= 50) return scaled ? num(props.share_area_r50) || 0 : (num(props.any_r50) ? 1 : 0);
  if (threshold <= 64) return scaled ? num(props.share_area_r64) || 0 : (num(props.any_r64) ? 1 : 0);
  return 0;
}
function windScore(props) {
  const threshold = Number(controls.windThreshold.value);
  const radius = Number(controls.distanceRadius.value);
  const scaled = controls.scaleWind.checked;
  const bucket = selectedBucket(radius);
  const maxWind = num(props[`max_track_wind_within_${bucket}km`]);
  const dist = num(props.centroid_min_distance_to_track_km);
  let distanceScore = 0;
  if (maxWind !== null && dist !== null && maxWind >= threshold && dist <= radius) {
    if (scaled) {
      const excess = threshold >= 155 ? 1 : clamp((maxWind - threshold) / Math.max(1, 155 - threshold));
      const proximity = radius <= 0 ? 1 : clamp(1 - dist / radius);
      distanceScore = clamp(Math.max(0.25, excess) * proximity);
    } else {
      distanceScore = 1;
    }
  }
  return clamp(Math.max(distanceScore, swathScore(props, threshold, scaled)));
}
function metricValues(metric) {
  return MUNICIPALITIES.features.map(f => num(f.properties[metric])).filter(v => v !== null);
}
function normalizeMetric(value, metric) {
  const n = num(value);
  if (n === null) return null;
  const vals = metricValues(metric);
  if (!vals.length) return null;
  const min = Math.min(...vals), max = Math.max(...vals);
  if (max === min) return 0;
  return clamp((n - min) / (max - min));
}
function rainScore(props) {
  return normalizeMetric(props[controls.rainMetric.value], controls.rainMetric.value) ?? 0;
}
function deathValues() {
  return STATE_IMPACTS
    .filter(r => r.matched_dashboard_state)
    .map(r => num(r.deaths_per_capita))
    .filter(v => v !== null);
}
function deathScoreValue(value) {
  const n = num(value);
  if (n === null) return 0;
  const vals = deathValues();
  if (!vals.length) return 0;
  const min = Math.min(...vals), max = Math.max(...vals);
  if (max === min) return 0;
  return clamp((n - min) / (max - min));
}
function stateImpact(key) {
  return impactByState.get(key) || null;
}
function hasDeathDataForState(key) {
  const rec = stateImpact(key);
  return !!rec && num(rec.deaths_per_capita) !== null;
}
function deathScoreForState(key) {
  const rec = stateImpact(key);
  return rec ? deathScoreValue(rec.deaths_per_capita) : 0;
}
function deathScore(props) {
  return deathScoreForState(stateKey(props));
}
function yangParagMode() {
  return controls.riskMode.value === 'yang_parag';
}
function yangGridIntensity(row) {
  const x = num(row.x_gjst);
  return x === null ? 0 : clamp(x / YANG_X_SCALE);
}
function yangGridIsOriginalTreated(row) {
  return !!row.is_original_treated;
}
function yangGridIsExpanded(row) {
  if (yangGridIsOriginalTreated(row) || !controls.yangExpand.checked) return false;
  const km = num(row.nearest_original_treated_grid_km);
  return km !== null && km <= Number(controls.yangExpandRadius.value);
}
function yangGridEffectiveTreated(row) {
  return yangGridIsOriginalTreated(row) || yangGridIsExpanded(row);
}
function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    const crosses = (yi > lat) !== (yj > lat);
    if (crosses && lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi) inside = !inside;
  }
  return inside;
}
function pointInPolygon(lon, lat, polygon) {
  if (!polygon.length || !pointInRing(lon, lat, polygon[0])) return false;
  return !polygon.slice(1).some(ring => pointInRing(lon, lat, ring));
}
function pointInGeometry(lon, lat, geometry) {
  if (!geometry) return false;
  if (geometry.type === 'Polygon') return pointInPolygon(lon, lat, geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.some(poly => pointInPolygon(lon, lat, poly));
  return false;
}
function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad;
  const dLon = (lon2 - lon1) * toRad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
}
function pointSegmentDistanceKm(lon, lat, a, b) {
  const kmLat = 111.32;
  const kmLon = 111.32 * Math.cos(lat * Math.PI / 180);
  const ax = (a[0] - lon) * kmLon, ay = (a[1] - lat) * kmLat;
  const bx = (b[0] - lon) * kmLon, by = (b[1] - lat) * kmLat;
  const dx = bx - ax, dy = by - ay;
  const denom = dx * dx + dy * dy;
  const t = denom ? clamp(-(ax * dx + ay * dy) / denom, 0, 1) : 0;
  const px = ax + t * dx, py = ay + t * dy;
  return Math.sqrt(px * px + py * py);
}
function ringDistanceKm(lon, lat, ring) {
  let best = Infinity;
  for (let i = 1; i < ring.length; i++) {
    best = Math.min(best, pointSegmentDistanceKm(lon, lat, ring[i - 1], ring[i]));
  }
  return best;
}
function geometryDistanceKm(lon, lat, geometry) {
  if (pointInGeometry(lon, lat, geometry)) return 0;
  const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : (geometry?.coordinates || []);
  let best = Infinity;
  for (const polygon of polygons) {
    for (const ring of polygon) best = Math.min(best, ringDistanceKm(lon, lat, ring));
  }
  return Number.isFinite(best) ? best : Infinity;
}
function yangDistances(props) {
  const key = props.muni_key;
  if (yangDistanceCache.has(key)) return yangDistanceCache.get(key);
  const lat0 = num(props.yang_rep_lat);
  const lon0 = num(props.yang_rep_lon);
  const rows = YANG_PARAG_GRID.map(row => {
    const lat = num(row.latitude), lon = num(row.longitude);
    const distanceKm = lat === null || lon === null || lat0 === null || lon0 === null
      ? Infinity
      : haversineKm(lat0, lon0, lat, lon);
    return { row, distanceKm };
  });
  yangDistanceCache.set(key, rows);
  return rows;
}
function nearer(a, b) {
  if (!a) return b;
  if (!b) return a;
  return b.distanceKm < a.distanceKm ? b : a;
}
function yangClassification(props) {
  let nearestAny = null;
  let nearestOriginalTreated = null;
  let nearestOriginalControl = null;
  let nearestEffectiveTreated = null;
  let nearestEffectiveControl = null;
  for (const item of yangDistances(props)) {
    const original = yangGridIsOriginalTreated(item.row);
    const effective = yangGridEffectiveTreated(item.row);
    const rec = { ...item, original, expanded: yangGridIsExpanded(item.row), effective, intensity: yangGridIntensity(item.row) };
    nearestAny = nearer(nearestAny, rec);
    if (original) nearestOriginalTreated = nearer(nearestOriginalTreated, rec);
    else nearestOriginalControl = nearer(nearestOriginalControl, rec);
    if (effective) nearestEffectiveTreated = nearer(nearestEffectiveTreated, rec);
    else nearestEffectiveControl = nearer(nearestEffectiveControl, rec);
  }
  const baseTreated = !!nearestOriginalTreated && (!nearestOriginalControl || nearestOriginalTreated.distanceKm < nearestOriginalControl.distanceKm);
  const effectiveTreated = !!nearestEffectiveTreated && (!nearestEffectiveControl || nearestEffectiveTreated.distanceKm < nearestEffectiveControl.distanceKm);
  const source = baseTreated ? 'original' : (effectiveTreated ? 'expanded' : 'control');
  const nearest = source === 'original'
    ? nearestOriginalTreated
    : source === 'expanded'
      ? nearestEffectiveTreated
      : (nearestEffectiveControl || nearestOriginalControl || nearestAny);
  const comparisonControl = source === 'original' ? nearestOriginalControl : nearestEffectiveControl;
  const marginKm = nearest && comparisonControl ? comparisonControl.distanceKm - nearest.distanceKm : null;
  return {
    treated: source !== 'control',
    source,
    score: source === 'control' ? 0 : 1,
    nearest,
    nearestOriginalTreated,
    nearestOriginalControl,
    nearestEffectiveTreated,
    nearestEffectiveControl,
    marginKm
  };
}
function yangParagScore(props) {
  return yangClassification(props).score;
}
function deathStateMode() {
  return controls.riskMode.value === 'death';
}
function riskScore(props) {
  const mode = controls.riskMode.value;
  if (mode === 'best') return windScore(props);
  if (mode === 'rain') return rainScore(props);
  if (mode === 'death') return deathScore(props);
  if (mode === 'yang_parag') return yangParagScore(props);
  const w = Number(controls.riskWeight.value);
  const d = Number(controls.deathWeight.value);
  const base = clamp(w * windScore(props) + (1 - w) * rainScore(props));
  return clamp((1 - d) * base + d * deathScore(props));
}
function mean(values) {
  const vals = values.filter(v => v !== null && Number.isFinite(v));
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
function fitLogTrend(points) {
  if (!points.length) return null;
  if (points.length === 1) {
    const only = points[0].logValue;
    return { predict: year => only, annualPct: null };
  }
  const xbar = mean(points.map(p => p.year));
  const ybar = mean(points.map(p => p.logValue));
  const sxx = points.reduce((s, p) => s + (p.year - xbar) ** 2, 0);
  if (sxx < 1e-9) return { predict: year => ybar, annualPct: null };
  const slope = points.reduce((s, p) => s + (p.year - xbar) * (p.logValue - ybar), 0) / sxx;
  const intercept = ybar - slope * xbar;
  return { predict: year => intercept + slope * year, annualPct: 100 * (Math.exp(slope) - 1) };
}
function ntlChangeMetric(muni) {
  const arr = collapsed.byMuni.get(muni) || [];
  const baselineYears = selectedBaselineYears();
  const comparisonYears = selectedComparisonYears();
  const byYear = new Map(arr.map(r => [r.year, r.stable_sum]));
  const baselinePoints = baselineYears
    .map(year => ({ year, value: byYear.get(year) }))
    .filter(d => d.value !== undefined && d.value !== null)
    .map(d => ({ year: d.year, value: d.value, logValue: Math.log1p(Math.max(0, d.value)) }));
  const comparisonPoints = comparisonYears
    .map(year => ({ year, value: byYear.get(year) }))
    .filter(d => d.value !== undefined && d.value !== null)
    .map(d => ({ year: d.year, value: d.value, logValue: Math.log1p(Math.max(0, d.value)) }));
  if (!baselinePoints.length || !comparisonPoints.length) return { category: 'insufficient' };
  const trend = fitLogTrend(baselinePoints);
  if (!trend) return { category: 'insufficient' };
  const anchorPoint = baselinePoints.slice().sort((a, b) => b.year - a.year)[0];
  const actualMeanLog = mean(comparisonPoints.map(d => d.logValue));
  const predictedMeanLog = mean(comparisonPoints.map(d => trend.predict(d.year)));
  const anchorPct = 100 * (Math.exp(actualMeanLog - anchorPoint.logValue) - 1);
  const trendPct = 100 * (Math.exp(actualMeanLog - predictedMeanLog) - 1);
  let simplePct = null;
  let logSafePct = 100 * (Math.exp(actualMeanLog - anchorPoint.logValue) - 1);
  if (baselineYears.length === 1 && comparisonYears.length === 1 && anchorPoint.value > 0) {
    simplePct = 100 * (comparisonPoints[0].value - anchorPoint.value) / anchorPoint.value;
  }
  const maxSelectedYear = Math.max(...comparisonYears);
  const maxSelectedPoint = comparisonPoints.find(d => d.year === maxSelectedYear);
  const yearsToMax = maxSelectedPoint ? maxSelectedPoint.year - anchorPoint.year : null;
  const growthToMaxPct = maxSelectedPoint && yearsToMax && yearsToMax > 0
    ? 100 * (Math.exp((maxSelectedPoint.logValue - anchorPoint.logValue) / yearsToMax) - 1)
    : null;
  const displayedAnchorPct = simplePct !== null ? simplePct : anchorPct;
  let category = 'growth';
  if (displayedAnchorPct < -1) category = 'loss';
  else if (trendPct < -1) category = 'slowdown';
  return {
    category,
    anchorPct: displayedAnchorPct,
    trendPct,
    simplePct,
    logSafePct,
    baselineYears,
    comparisonYears,
    meanPreGrowthPct: trend.annualPct,
    growthToMaxPct,
    maxSelectedYear,
    value1992: byYear.get(1992) ?? null,
    value1997: byYear.get(1997) ?? null,
    value1998: byYear.get(1998) ?? null,
    value1999: byYear.get(1999) ?? null,
    actualMean: mean(comparisonPoints.map(d => d.value)),
    predictedMean: Math.max(0, Math.exp(predictedMeanLog) - 1),
    anchorValue: anchorPoint.value
  };
}

function computeActive() {
  collapsed = collapsePanel();
  active = new Map();
  activeState = new Map();
  const threshold = preFilterThreshold();
  const cutoff = Number(controls.treatmentCutoff.value);
  const stateMode = deathStateMode();
  const yangMode = yangParagMode();
  for (const s of states) {
    const preMean = collapsed.statePreMean.get(s.key) ?? null;
    const score = deathScoreForState(s.key);
    const hasDeaths = hasDeathDataForState(s.key);
    const countrySet = selectedCountrySet();
    const stateSet = selectedStateSet();
    const geoSelected = countrySet.has(s.country_name) && (!stateSet || stateSet.has(s.key));
    const included = geoSelected && preMean !== null && preMean >= threshold && (!stateMode || hasDeaths);
    activeState.set(s.key, { geoSelected, preMean, score, hasDeaths, included, treated: included && score >= cutoff });
  }
  for (const f of MUNICIPALITIES.features) {
    const p = f.properties;
    const geoSelected = isGeoSelected(p);
    const stateStatus = activeState.get(stateKey(p));
    const preMean = stateMode ? (stateStatus?.preMean ?? null) : (collapsed.preMean.get(p.muni_key) ?? null);
    const yang = yangMode ? yangClassification(p) : null;
    const score = stateMode ? (stateStatus?.score ?? 0) : (yangMode ? (yang?.score ?? 0) : riskScore(p));
    const included = stateMode
      ? !!stateStatus?.included && geoSelected
      : geoSelected && preMean !== null && preMean >= threshold;
    const change = included ? ntlChangeMetric(p.muni_key) : { category: 'insufficient' };
    const treated = stateMode
      ? !!stateStatus?.treated
      : included && (yangMode ? !!yang?.treated : score >= cutoff);
    const treatmentClass = yangMode ? (yang?.source || 'control') : (treated ? 'treated' : 'control');
    active.set(p.muni_key, { geoSelected, preMean, score, included, treated, change, treatmentClass, yang });
  }
}

function ntlStyle(feature) {
  const st = active.get(feature.properties.muni_key);
  if (!st || !st.geoSelected) return { color: '#111827', weight: 0.45, fillColor: '#111827', fillOpacity: 0.44 };
  if (!st.included) return { color: '#111827', weight: 0.8, fillColor: '#111827', fillOpacity: 0.76 };
  return { color: '#334155', weight: 0.8, fillColor: ntlChangeColor(st.change), fillOpacity: 0.76 };
}
function exposureStyle(feature) {
  const st = active.get(feature.properties.muni_key);
  if (!st || !st.geoSelected) return { color: '#111827', weight: 0.45, fillColor: '#111827', fillOpacity: 0.44 };
  if (!st.included) return { color: '#111827', weight: 0.8, fillColor: '#111827', fillOpacity: 0.78 };
  if (yangParagMode()) {
    const fillColor = st.treatmentClass === 'original'
      ? TREATED_COLOR
      : st.treatmentClass === 'expanded'
        ? YANG_MUNI_EXPANDED_COLOR
        : YANG_CONTROL_COLOR;
    return {
      color: st.treated ? '#7f1d1d' : '#6b7280',
      weight: st.treated ? 1.2 : 0.55,
      fillColor,
      fillOpacity: st.treated ? 0.82 : 0.58
    };
  }
  return {
    color: st.treated ? TREATED_COLOR : CONTROL_COLOR,
    weight: st.treated ? 1.25 : 0.55,
    fillColor: st.treated ? TREATED_COLOR : CONTROL_COLOR,
    fillOpacity: st.treated ? 0.82 : 0.52
  };
}
function popupHtml(props) {
  const st = active.get(props.muni_key) || {};
  const yang = yangParagMode() ? (st.yang || yangClassification(props)) : null;
  const ymatch = yang?.nearest || null;
  const yrow = ymatch?.row || {};
  const yangRows = yang ? `
    <tr><td>Yang class</td><td><b>${escapeHtml(yang.source)}</b></td></tr>
    <tr><td>Nearest grid</td><td><b>${escapeHtml(yrow.grid_id)} (${fmt(yrow.latitude, 2)}, ${fmt(yrow.longitude, 2)})</b></td></tr>
    <tr><td>Grid country</td><td><b>${escapeHtml(yrow.country)}</b></td></tr>
    <tr><td>Source country</td><td><b>${escapeHtml(yrow.source_country || 'None')}</b></td></tr>
    <tr><td>Grid distance</td><td><b>${fmt(ymatch?.distanceKm, 1)} km</b></td></tr>
    <tr><td>Yang margin</td><td><b>${fmt(yang.marginKm, 1)} km</b></td></tr>
    <tr><td>x_gjst</td><td><b>${fmt(yrow.x_gjst, 6)}</b></td></tr>
    <tr><td>Grid intensity</td><td><b>${fmt(yangGridIntensity(yrow), 3)}</b></td></tr>
    <tr><td>Predicted wind</td><td><b>${fmt(yrow.pwind, 1)} kt</b></td></tr>
  ` : '';
  return `<b>${escapeHtml(muniName(props))}</b><table>
    <tr><td>Country</td><td><b>${escapeHtml(props.country_name)}</b></td></tr>
    <tr><td>Department</td><td><b>${escapeHtml(props.department_name)}</b></td></tr>
    <tr><td>Included</td><td><b>${st.included ? 'Yes' : 'No'}</b></td></tr>
    <tr><td>Treated</td><td><b>${st.treated ? 'Yes' : 'No'}</b></td></tr>
    <tr><td>Pre mean</td><td><b>${fmt(st.preMean, 1)}</b></td></tr>
    <tr><td>NTL change</td><td><b>${escapeHtml(st.change?.category || 'NA')} (${fmtPct(st.change?.trendPct)})</b></td></tr>
    <tr><td>Score</td><td><b>${fmt(st.score, 3)}</b></td></tr>
    <tr><td>Deaths</td><td><b>${fmt(props.impact_deaths, 0)}</b></td></tr>
    <tr><td>Deaths/capita</td><td><b>${fmt(props.deaths_per_capita, 6)}</b></td></tr>
    <tr><td>Rain total</td><td><b>${fmt(props.rain_total_mean_mm, 1)} mm</b></td></tr>
    <tr><td>Nearest wind</td><td><b>${fmt(props.nearest_track_wind_kt, 0)} kt</b></td></tr>
    ${yangRows}
  </table>`;
}

function yangPointStyle(row) {
  const intensity = yangGridIntensity(row);
  const original = yangGridIsOriginalTreated(row);
  const expanded = yangGridIsExpanded(row);
  const radius = original ? 4 + 8 * Math.sqrt(intensity) : (expanded ? 5.5 : 3.2);
  const fillColor = original ? YANG_GRID_TREATED_COLOR : (expanded ? YANG_GRID_EXPANDED_COLOR : '#9ca3af');
  return {
    radius,
    color: original ? '#7f1d1d' : (expanded ? '#1d4ed8' : '#6b7280'),
    weight: original || expanded ? 1.35 : 0.7,
    fillColor,
    fillOpacity: original || expanded ? 0.86 : 0.56
  };
}
function yangPointPopup(row) {
  return `<b>Yang-Parag grid ${escapeHtml(row.grid_id)}</b><table>
    <tr><td>Country</td><td><b>${escapeHtml(row.country)}</b></td></tr>
    <tr><td>Source country</td><td><b>${escapeHtml(row.source_country || 'None')}</b></td></tr>
    <tr><td>Class</td><td><b>${yangGridIsOriginalTreated(row) ? 'Original treated' : (yangGridIsExpanded(row) ? 'Expanded treated' : 'Control')}</b></td></tr>
    <tr><td>Latitude</td><td><b>${fmt(row.latitude, 2)}</b></td></tr>
    <tr><td>Longitude</td><td><b>${fmt(row.longitude, 2)}</b></td></tr>
    <tr><td>Cell</td><td><b>${fmt(row.grid_step_degrees, 2)} x ${fmt(row.grid_step_degrees, 2)} degrees</b></td></tr>
    <tr><td>Grid pop</td><td><b>${fmt(row.grid_pop, 0)}</b></td></tr>
    <tr><td>Total country pop</td><td><b>${fmt(row.total_country_pop, 0)}</b></td></tr>
    <tr><td>x_gjst</td><td><b>${fmt(row.x_gjst, 6)}</b></td></tr>
    <tr><td>Score scale</td><td><b>${fmt(yangGridIntensity(row), 3)}</b></td></tr>
    <tr><td>Predicted wind</td><td><b>${fmt(row.pwind, 1)} kt</b></td></tr>
    <tr><td>Nearest purple grid</td><td><b>${fmt(row.nearest_original_treated_grid_km, 1)} km</b></td></tr>
    <tr><td>Distance to segment</td><td><b>${fmt(row.dist, 1)} km</b></td></tr>
    <tr><td>Affecting segments</td><td><b>${fmt(row.num_affecting, 0)}</b></td></tr>
    <tr><td>Storm time</td><td><b>${escapeHtml(row.name)} ${fmt(row.month, 0)}/${fmt(row.day, 0)} ${fmt(row.hour, 0)}:00</b></td></tr>
    <tr><td>Best-track wind</td><td><b>${fmt(row.wspeed, 0)} kt</b></td></tr>
    <tr><td>R34 radius</td><td><b>${fmt(row.pradius34, 1)} km</b></td></tr>
  </table>`;
}
function buildYangParagLayer() {
  return L.layerGroup(YANG_PARAG_GRID.map(row => {
    const marker = L.circleMarker([row.latitude, row.longitude], yangPointStyle(row));
    marker.bindPopup(() => yangPointPopup(row));
    marker.yangRow = row;
    return marker;
  }));
}
function refreshYangParagLayer() {
  if (!yangParagLayer) return;
  if (exposureMap) {
    const shouldShow = yangParagMode();
    const isShown = exposureMap.hasLayer(yangParagLayer);
    if (shouldShow && !isShown) yangParagLayer.addTo(exposureMap);
    if (!shouldShow && isShown) exposureMap.removeLayer(yangParagLayer);
  }
  yangParagLayer.eachLayer(layer => {
    if (layer.yangRow && layer.setStyle) layer.setStyle(yangPointStyle(layer.yangRow));
  });
}

function initMaps() {
  ntlMap = L.map('ntlMap', { preferCanvas: true });
  exposureMap = L.map('exposureMap', { preferCanvas: true });
  for (const map of [ntlMap, exposureMap]) {
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  }
  if (RAIN_OVERLAY && RAIN_OVERLAY.bounds_wgs84) {
    const b = RAIN_OVERLAY.bounds_wgs84;
    ntlRainLayer = L.imageOverlay(RAIN_OVERLAY.data_uri, [[b.south, b.west], [b.north, b.east]], { opacity: 0.42 }).addTo(ntlMap);
    exposureRainLayer = L.imageOverlay(RAIN_OVERLAY.data_uri, [[b.south, b.west], [b.north, b.east]], { opacity: 0.55 }).addTo(exposureMap);
  }
  ntlMuniLayer = L.geoJSON(MUNICIPALITIES, { style: ntlStyle, onEachFeature: (feature, layer) => layer.bindPopup(() => popupHtml(feature.properties)) }).addTo(ntlMap);
  exposureMuniLayer = L.geoJSON(MUNICIPALITIES, { style: exposureStyle, onEachFeature: (feature, layer) => layer.bindPopup(() => popupHtml(feature.properties)) }).addTo(exposureMap);
  addExposureLayers(exposureMap);
  addExposureLayers(ntlMap, false);
  ntlMap.fitBounds(ntlMuniLayer.getBounds(), { padding: [18, 18] });
  exposureMap.fitBounds(exposureMuniLayer.getBounds(), { padding: [18, 18] });
  addLegend(ntlMap, 'NTL relative change', 'Red = loss, yellow = slower than pre-trend, green = same/faster; black = excluded');
  addLegend(exposureMap, 'Treatment', '<span style="color:#b91c1c">&#9632;</span> Treated &nbsp; <span style="color:#15803d">&#9632;</span> Control in score modes<br>Yang-Parag: red = original, yellow = expanded, gray = control; grid red/blue/gray<br>Black = excluded/unmatched');
}
function addExposureLayers(map, addControl = true) {
  const trackLine = L.geoJSON(TRACK_LINE, { style: { color: '#111827', weight: 3, opacity: 0.9 } }).addTo(map);
  const trackPoints = L.geoJSON(TRACK_POINTS, {
    pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: 3.5, color: '#111827', fillColor: '#fff', fillOpacity: 1, weight: 1.2 }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`<b>${p.iso_time || ''}</b><br>Wind: ${fmt(p.wind_kt, 0)} kt<br>Pressure: ${fmt(p.pressure_mb, 0)} mb`);
    }
  }).addTo(map);
  const r34 = L.geoJSON(SWATHS.r34, { style: { color: '#0f766e', weight: 1.2, fillColor: '#0f766e', fillOpacity: 0.1 } }).addTo(map);
  const r50 = L.geoJSON(SWATHS.r50, { style: { color: '#d97706', weight: 1.2, fillColor: '#d97706', fillOpacity: 0.1 } }).addTo(map);
  const r64 = L.geoJSON(SWATHS.r64, { style: { color: '#b91c1c', weight: 1.2, fillColor: '#b91c1c', fillOpacity: 0.1 } }).addTo(map);
  const yangLayer = addControl && YANG_PARAG_GRID.length ? buildYangParagLayer() : null;
  if (yangLayer) {
    yangParagLayer = yangLayer;
    if (yangParagMode()) yangParagLayer.addTo(map);
  }
  if (addControl) {
    const overlays = { 'Municipalities': exposureMuniLayer, 'Mitch track': trackLine, 'Track points': trackPoints, 'R34 swath': r34, 'R50 swath': r50, 'R64 swath': r64 };
    if (exposureRainLayer) overlays['CHIRPS overlay'] = exposureRainLayer;
    L.control.layers({}, overlays, { collapsed: false }).addTo(map);
  }
}
function addLegend(map, title, text, blue = false) {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = function() {
    const div = L.DomUtil.create('div', 'legend');
    div.innerHTML = `<b>${title}</b><div class="legend-bar${blue ? ' blue' : ''}"></div>${text}`;
    return div;
  };
  legend.addTo(map);
}

function currentMuniRows() {
  return collapsed.rows.filter(r => {
    const st = active.get(r.muni_key);
    return st && st.included;
  });
}
function currentStateRows() {
  return collapsed.stateRows.filter(r => {
    const st = activeState.get(r.state_key);
    return st && st.included;
  });
}
function currentSampleRows() {
  return deathStateMode() ? currentStateRows() : currentMuniRows();
}
function rowWithTreatment(r) {
  if (deathStateMode()) {
    const st = activeState.get(r.state_key) || {};
    return { ...r, muni_key: r.state_key, treated: !!st.treated, country_name: r.country_name };
  }
  const st = active.get(r.muni_key);
  const p = featureByMuni.get(r.muni_key).properties;
  return { ...r, treated: !!st.treated, country_name: p.country_name };
}
function analysisUnitSingular() {
  return deathStateMode() ? 'state' : 'municipality';
}
function analysisUnitPlural() {
  return deathStateMode() ? 'states' : 'municipalities';
}
function sampleStats() {
  if (deathStateMode()) {
    const included = [...activeState.entries()].filter(([, st]) => st.included);
    const treated = included.filter(([, st]) => st.treated).length;
    const control = included.length - treated;
    return { included: included.length, treated, control, rows: currentSampleRows().length };
  }
  const included = [...active.entries()].filter(([, st]) => st.included);
  const treated = included.filter(([, st]) => st.treated).length;
  const control = included.length - treated;
  return { included: included.length, treated, control, rows: currentSampleRows().length };
}
function updateLabels() {
  updateModeControls();
  const unit = analysisUnitPlural();
  document.getElementById('preFilterValue').textContent = preFilterThreshold().toLocaleString();
  document.getElementById('distanceRadiusValue').textContent = controls.distanceRadius.value;
  document.getElementById('riskWeightValue').textContent = Number(controls.riskWeight.value).toFixed(2);
  document.getElementById('deathWeightValue').textContent = Number(controls.deathWeight.value).toFixed(2);
  document.getElementById('treatmentCutoffValue').textContent = Number(controls.treatmentCutoff.value).toFixed(2);
  document.getElementById('yangExpandRadiusValue').textContent = controls.yangExpandRadius.value;
  const s = sampleStats();
  document.getElementById('sampleSummary').innerHTML = `${s.included.toLocaleString()} included ${unit}<br>${s.rows.toLocaleString()} ${analysisUnitSingular()}-years`;
  document.getElementById('coverageNote').innerHTML =
    `<b>Boundary join:</b> ${MANIFEST.matched_ntl_municipalities || MANIFEST.matched_municipalities} of ${MANIFEST.raw_ntl_municipalities || MANIFEST.ntl_municipalities} NTL municipalities matched. Unmatched units are reported but not drawn.`;
}
function metricCards(target, rows) {
  document.getElementById(target).innerHTML = rows.map(r => `<div class="metric"><span>${r[0]}</span><b>${r[1]}</b></div>`).join('');
}

function updateNTL() {
  const rows = currentMuniRows();
  const s = sampleStats();
  const baseline = selectedBaselineYears();
  const comparison = selectedComparisonYears();
  metricCards('ntlMetrics', [
    ['Included munis', s.included.toLocaleString()],
    ['Municipality-years', s.rows.toLocaleString()],
    ['Satellites', activeSatSet().size],
    ['Pre threshold', fmtInt(preFilterThreshold())]
  ]);
  document.getElementById('yearComparisonSummary').textContent =
    `${baseline.join(', ')} baseline vs ${comparison.join(', ')} comparison. ` +
    (baseline.length === 1 && comparison.length === 1
      ? 'Ranking uses simple percent change, with a log-safe companion.'
      : comparison.length === 1
        ? 'Ranking compares the comparison year with its value predicted from the selected baseline trend.'
        : 'Ranking compares the comparison-window average with the average predicted from the selected baseline trend.');
  drawNTLCharts(rows);
  updateRankingTable(rows);
}
function activeLevels() {
  const countrySet = selectedCountrySet();
  const stateSet = selectedStateSet();
  const muniSet = selectedMuniSet();
  if (muniSet && muniSet.size) return ['municipality'];
  if (stateSet && stateSet.size) return ['state', 'municipality'];
  if (countrySet.size > 1) return ['country', 'state', 'municipality'];
  return ['state', 'municipality'];
}
function unitKey(level, props) {
  if (level === 'country') return props.country_name;
  if (level === 'state') return stateKey(props);
  return props.muni_key;
}
function unitLabel(level, props) {
  if (level === 'country') return props.country_name;
  if (level === 'state') return `${props.department_name}, ${props.country_name}`;
  return `${muniName(props)}, ${props.department_name}`;
}
function aggregateCollapsedSeries(level, logged) {
  const acc = new Map();
  for (const r of currentMuniRows()) {
    const props = featureByMuni.get(r.muni_key).properties;
    const key = unitKey(level, props);
    const label = unitLabel(level, props);
    const groupKey = `${key}|${r.year}`;
    const rec = acc.get(groupKey) || { key, label, year: r.year, value: 0 };
    rec.value += r.stable_sum;
    acc.set(groupKey, rec);
  }
  const series = new Map();
  for (const rec of acc.values()) {
    if (!series.has(rec.key)) series.set(rec.key, { label: rec.label, years: new Map() });
    series.get(rec.key).years.set(rec.year, logged ? Math.log1p(Math.max(0, rec.value)) : rec.value);
  }
  return [...series.entries()].map(([key, rec]) => ({
    key,
    label: rec.label,
    x: YEARS,
    y: YEARS.map(year => rec.years.get(year) ?? null)
  })).sort((a, b) => a.label.localeCompare(b.label));
}
function aggregateSatelliteSeries(level, logged) {
  const satSet = activeSatSet();
  const acc = new Map();
  for (const r of NTL_RAW) {
    if (!satSet.has(r.satellite)) continue;
    const st = active.get(r.muni_key);
    if (!st || !st.included) continue;
    const props = featureByMuni.get(r.muni_key).properties;
    const key = unitKey(level, props);
    const label = unitLabel(level, props);
    const groupKey = `${key}|${r.satellite}|${r.year}`;
    const rec = acc.get(groupKey) || { key: `${key}|${r.satellite}`, label: `${label} - ${r.satellite}`, year: Number(r.year), value: 0 };
    const v = num(r.stable_sum);
    if (v === null) continue;
    rec.value += v;
    acc.set(groupKey, rec);
  }
  const series = new Map();
  for (const rec of acc.values()) {
    if (!series.has(rec.key)) series.set(rec.key, { label: rec.label, years: new Map() });
    series.get(rec.key).years.set(rec.year, logged ? Math.log1p(Math.max(0, rec.value)) : rec.value);
  }
  return [...series.entries()].map(([key, rec]) => ({
    key,
    label: rec.label,
    x: YEARS,
    y: YEARS.map(year => rec.years.get(year) ?? null)
  })).sort((a, b) => a.label.localeCompare(b.label));
}
function drawNTLCharts(rows) {
  const container = document.getElementById('ntlGraphGrid');
  const levels = activeLevels();
  if (!rows.length) {
    container.innerHTML = '<div class="tiny">No included NTL rows for the current selections.</div>';
    return;
  }
  container.innerHTML = '';
  const deagg = controls.deaggregateSats.checked;
  levels.forEach((level, levelIdx) => {
    ['stable', 'log'].forEach(kind => {
      const id = `ntlChart_${level}_${kind}_${levelIdx}`;
      const cell = document.createElement('div');
      cell.id = id;
      cell.className = 'chart-cell';
      container.appendChild(cell);
      const logged = kind === 'log';
      const collapsedSeries = aggregateCollapsedSeries(level, logged);
      const allowSatelliteLines = deagg && collapsedSeries.length <= 20;
      const series = allowSatelliteLines ? aggregateSatelliteSeries(level, logged) : collapsedSeries;
      const traces = series.map(s => ({
        type: series.length > 80 ? 'scattergl' : 'scatter',
        mode: 'lines',
        name: s.label,
        x: s.x,
        y: s.y,
        opacity: allowSatelliteLines ? 0.42 : 0.82,
        line: { width: allowSatelliteLines ? 1 : (series.length > 35 ? 1.2 : 2) }
      }));
      const suffix = deagg && !allowSatelliteLines ? ' (satellite lines off: >20 units)' : '';
      Plotly.react(id, traces, {
        title: { text: `${levelLabel(level)} - ${logged ? 'log1p NTL' : 'NTL sum'}${suffix}`, x: 0, font: { size: 12 } },
        margin: { l: 52, r: 12, t: 32, b: 34 },
        yaxis: { title: logged ? 'log1p(sum)' : 'stable_sum' },
        shapes: impactYearShapes(),
        showlegend: series.length <= 28,
        legend: { orientation: 'h', y: -0.25 }
      }, { displayModeBar: false, responsive: true });
    });
  });
}
function levelLabel(level) {
  if (level === 'country') return 'Countries';
  if (level === 'state') return 'States / departments';
  return 'Municipalities';
}
function muniMetrics(rows) {
  const out = [];
  for (const [muni, arr] of collapsed.byMuni.entries()) {
    const st = active.get(muni);
    if (!st || !st.included) continue;
    const p = featureByMuni.get(muni).properties;
    out.push({ muni, props: p, preMean: st.preMean, score: st.score, treated: st.treated, change: st.change });
  }
  return out;
}
function updateRankingTable(rows) {
  const rank = { loss: 0, slowdown: 1, growth: 2, insufficient: 3 };
  const metrics = muniMetrics(rows)
    .sort((a, b) => (rank[a.change?.category || 'insufficient'] - rank[b.change?.category || 'insufficient']) || ((a.change?.trendPct ?? 999999) - (b.change?.trendPct ?? 999999)))
    .slice(0, 180);
  const html = [`<tr><th>Municipality</th><th>Department</th><th>Country</th><th>NTL class</th><th>Treatment / risk</th><th>Actual vs baseline</th><th>1992 value</th><th>1997 value</th><th>Mean pre growth</th><th>1998 value</th><th>1999 value</th><th>Growth to max selected</th><th>Actual comp. mean</th><th>Predicted comp. mean</th></tr>`]
    .concat(metrics.map(d => {
      const color = ntlChangeColor(d.change);
      const treatment = `${d.treated ? 'Treated' : 'Control'} (${fmt(d.score, 3)})`;
      return `<tr><td>${escapeHtml(d.props.municipality_name)}</td><td>${escapeHtml(d.props.department_name)}</td><td>${escapeHtml(d.props.country_name)}</td><td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${color};margin-right:5px;"></span>${escapeHtml(d.change?.category || 'NA')}</td><td>${treatment}</td><td>${fmtPct(d.change?.anchorPct)}</td><td>${fmt(d.change?.value1992, 1)}</td><td>${fmt(d.change?.value1997, 1)}</td><td>${fmtPct(d.change?.meanPreGrowthPct)}</td><td>${fmt(d.change?.value1998, 1)}</td><td>${fmt(d.change?.value1999, 1)}</td><td>${fmtPct(d.change?.growthToMaxPct)}</td><td>${fmt(d.change?.actualMean, 1)}</td><td>${fmt(d.change?.predictedMean, 1)}</td></tr>`;
    }));
  document.getElementById('ntlRankTable').innerHTML = html.join('');
}

function updateExposure() {
  const values = deathStateMode()
    ? [...activeState.values()].filter(d => d.included)
    : [...active.values()].filter(d => d.included);
  const treated = values.filter(d => d.treated);
  const control = values.filter(d => !d.treated);
  const unit = analysisUnitPlural();
  metricCards('exposureMetrics', [
    [`Treated ${unit}`, treated.length.toLocaleString()],
    [`Control ${unit}`, control.length.toLocaleString()],
    [yangParagMode() ? 'Expansion' : 'Cutoff', yangParagMode() ? (controls.yangExpand.checked ? `${controls.yangExpandRadius.value} km` : 'Off') : Number(controls.treatmentCutoff.value).toFixed(2)],
    ['Risk mode', controls.riskMode.options[controls.riskMode.selectedIndex].text]
  ]);
  Plotly.react('riskDistribution', [
    { type: 'histogram', name: 'Control', x: control.map(d => d.score), opacity: 0.7, marker: { color: CONTROL_COLOR }, nbinsx: 24 },
    { type: 'histogram', name: 'Treated', x: treated.map(d => d.score), opacity: 0.78, marker: { color: TREATED_COLOR }, nbinsx: 24 }
  ], {
    barmode: 'overlay',
    margin: { l: 42, r: 14, t: 8, b: 36 },
    shapes: yangParagMode() ? [] : [{ type: 'line', x0: Number(controls.treatmentCutoff.value), x1: Number(controls.treatmentCutoff.value), y0: 0, y1: 1, yref: 'paper', line: { color: '#111827', dash: 'dash' } }],
    xaxis: { title: deathStateMode() ? 'Deaths per capita risk score' : (yangParagMode() ? 'Yang-Parag nearest-grid treatment' : 'Selected risk score'), range: [0, 1] },
    yaxis: { title: unit[0].toUpperCase() + unit.slice(1) },
    legend: { orientation: 'h', y: -0.25 }
  }, { displayModeBar: false, responsive: true });
  drawTrackPlot();
  updateExposureTable();
}
function drawTrackPlot() {
  if (yangParagMode()) {
    const rows = YANG_PARAG_GRID
      .map(r => ({ ...r, intensity: yangGridIntensity(r), original: yangGridIsOriginalTreated(r), expanded: yangGridIsExpanded(r) }))
      .sort((a, b) => b.intensity - a.intensity)
      .slice(0, 35)
      .reverse();
    Plotly.react('trackPlot', [{
      type: 'bar',
      orientation: 'h',
      name: 'x_gjst score scale',
      y: rows.map(r => `${r.grid_id} - ${r.country}`),
      x: rows.map(r => r.intensity),
      marker: { color: rows.map(r => r.original ? YANG_GRID_TREATED_COLOR : (r.expanded ? YANG_GRID_EXPANDED_COLOR : '#9ca3af')) },
      customdata: rows.map(r => [r.x_gjst, r.pwind, r.grid_pop, r.latitude, r.longitude, r.original ? 'original treated' : (r.expanded ? 'expanded treated' : 'control')]),
      hovertemplate: '%{y}<br>%{customdata[5]}<br>score scale: %{x:.3f}<br>x_gjst: %{customdata[0]:.6f}<br>pwind: %{customdata[1]:.1f} kt<br>grid pop: %{customdata[2]:,.0f}<br>lat/lon: %{customdata[3]:.2f}, %{customdata[4]:.2f}<extra></extra>'
    }], {
      title: { text: 'Yang-Parag grid points, sorted by x_gjst', x: 0, font: { size: 12 } },
      margin: { l: 138, r: 16, t: 30, b: 34 },
      xaxis: { title: 'Robust normalized x_gjst', range: [0, 1] },
      yaxis: { automargin: true }
    }, { displayModeBar: false, responsive: true });
    return;
  }
  if (deathStateMode()) {
    const rows = states.map(s => {
      const impact = stateImpact(s.key) || {};
      return { ...s, ...impact, ...activeState.get(s.key) };
    })
      .filter(r => r.geoSelected && num(r.deaths_per_capita) !== null)
      .sort((a, b) => (b.deaths_per_capita ?? -1) - (a.deaths_per_capita ?? -1))
      .slice(0, 35)
      .reverse();
    Plotly.react('trackPlot', [{
      type: 'bar',
      orientation: 'h',
      name: 'Deaths per capita',
      y: rows.map(r => `${r.department_name}, ${r.country_name}`),
      x: rows.map(r => r.deaths_per_capita),
      marker: { color: rows.map(r => r.treated ? TREATED_COLOR : CONTROL_COLOR) },
      customdata: rows.map(r => [r.impact_deaths, r.impact_population]),
      hovertemplate: '%{y}<br>Deaths/capita: %{x:.6f}<br>Deaths: %{customdata[0]:,.0f}<br>Population: %{customdata[1]:,.0f}<extra></extra>'
    }], {
      title: { text: 'State deaths per capita, sorted', x: 0, font: { size: 12 } },
      margin: { l: 148, r: 16, t: 30, b: 34 },
      xaxis: { title: 'Deaths per capita' },
      yaxis: { automargin: true }
    }, { displayModeBar: false, responsive: true });
    return;
  }
  const x = TRACK_ROWS.map(d => d.iso_time);
  Plotly.react('trackPlot', [
    { type: 'scatter', mode: 'lines+markers', name: 'Wind kt', x, y: TRACK_ROWS.map(d => num(d.wind_kt)), marker: { size: 4 }, line: { color: '#b91c1c' } },
    { type: 'scatter', mode: 'lines+markers', name: 'Pressure mb', x, y: TRACK_ROWS.map(d => num(d.pressure_mb)), yaxis: 'y2', marker: { size: 4 }, line: { color: '#2563eb' } }
  ], {
    margin: { l: 42, r: 46, t: 8, b: 36 },
    yaxis: { title: 'kt', rangemode: 'tozero' },
    yaxis2: { title: 'mb', overlaying: 'y', side: 'right', autorange: 'reversed' },
    legend: { orientation: 'h', y: -0.25 }
  }, { displayModeBar: false, responsive: true });
}
function updateExposureTable() {
  if (yangParagMode()) {
    const rows = MUNICIPALITIES.features.map(f => {
      const p = f.properties;
      const st = active.get(p.muni_key) || {};
      const yang = st.yang || yangClassification(p);
      const match = yang.nearest;
      return { ...p, ...st, yang, yangMatch: match, yangRow: match?.row || {} };
    })
      .filter(r => r.geoSelected)
      .sort((a, b) => (Number(b.treated) - Number(a.treated)) || ((b.yang?.marginKm ?? -999999) - (a.yang?.marginKm ?? -999999)))
      .slice(0, 250);
    const html = [`<tr><th>Municipality</th><th>Department</th><th>Country</th><th>Included</th><th>Treated</th><th>Yang class</th><th>Pre NTL</th><th>Nearest grid</th><th>Grid country</th><th>Source country</th><th>Distance km</th><th>Margin km</th><th>x_gjst</th><th>Intensity</th><th>Pred. wind kt</th><th>Grid pop</th></tr>`]
      .concat(rows.map(r => `<tr><td>${escapeHtml(r.municipality_name)}</td><td>${escapeHtml(r.department_name)}</td><td>${escapeHtml(r.country_name)}</td><td>${r.included ? 'Yes' : 'No'}</td><td>${r.treated ? 'Yes' : 'No'}</td><td>${escapeHtml(r.yang?.source || 'control')}</td><td>${fmt(r.preMean, 1)}</td><td>${escapeHtml(r.yangRow.grid_id)}</td><td>${escapeHtml(r.yangRow.country)}</td><td>${escapeHtml(r.yangRow.source_country || 'None')}</td><td>${fmt(r.yangMatch?.distanceKm, 1)}</td><td>${fmt(r.yang?.marginKm, 1)}</td><td>${fmt(r.yangRow.x_gjst, 6)}</td><td>${fmt(yangGridIntensity(r.yangRow), 3)}</td><td>${fmt(r.yangRow.pwind, 1)}</td><td>${fmt(r.yangRow.grid_pop, 0)}</td></tr>`));
    document.getElementById('exposureTable').innerHTML = html.join('');
    return;
  }
  if (deathStateMode()) {
    const rows = states.map(s => {
      const impact = stateImpact(s.key) || {};
      return { ...s, ...impact, ...activeState.get(s.key) };
    })
      .filter(r => r.geoSelected)
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
      .slice(0, 250);
    const html = [`<tr><th>State / Department</th><th>Country</th><th>Included</th><th>Treated</th><th>Score</th><th>Pre NTL</th><th>Deaths</th><th>Population</th><th>Deaths/capita</th><th>Death+disapp./capita</th></tr>`]
      .concat(rows.map(r => `<tr><td>${escapeHtml(r.department_name)}</td><td>${escapeHtml(r.country_name)}</td><td>${r.included ? 'Yes' : 'No'}</td><td>${r.treated ? 'Yes' : 'No'}</td><td>${fmt(r.score, 3)}</td><td>${fmt(r.preMean, 1)}</td><td>${fmt(r.impact_deaths, 0)}</td><td>${fmt(r.impact_population, 0)}</td><td>${fmt(r.deaths_per_capita, 6)}</td><td>${fmt(r.deaths_disappearances_per_capita, 6)}</td></tr>`));
    document.getElementById('exposureTable').innerHTML = html.join('');
    return;
  }
  const rows = MUNICIPALITIES.features.map(f => ({ ...f.properties, ...active.get(f.properties.muni_key) }))
    .filter(r => r.geoSelected)
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
    .slice(0, 250);
  const html = [`<tr><th>Municipality</th><th>Department</th><th>Country</th><th>Included</th><th>Treated</th><th>Score</th><th>Pre NTL</th><th>Deaths</th><th>Population</th><th>Deaths/capita</th><th>Wind kt</th><th>Rain total</th><th>Rain max daily</th></tr>`]
    .concat(rows.map(r => `<tr><td>${escapeHtml(r.municipality_name)}</td><td>${escapeHtml(r.department_name)}</td><td>${escapeHtml(r.country_name)}</td><td>${r.included ? 'Yes' : 'No'}</td><td>${r.treated ? 'Yes' : 'No'}</td><td>${fmt(r.score, 3)}</td><td>${fmt(r.preMean, 1)}</td><td>${fmt(r.impact_deaths, 0)}</td><td>${fmt(r.impact_population, 0)}</td><td>${fmt(r.deaths_per_capita, 6)}</td><td>${fmt(r.nearest_track_wind_kt, 0)}</td><td>${fmt(r.rain_total_mean_mm, 1)}</td><td>${fmt(r.rain_max_daily_mean_mm, 1)}</td></tr>`));
  document.getElementById('exposureTable').innerHTML = html.join('');
}

function updateResults() {
  enforceFERules();
  const rows = currentSampleRows().map(rowWithTreatment);
  const treatedUnits = new Set(rows.filter(r => r.treated).map(r => r.muni_key));
  const controlUnits = new Set(rows.filter(r => !r.treated).map(r => r.muni_key));
  const unit = analysisUnitPlural();
  metricCards('resultMetrics', [
    ['N', rows.length.toLocaleString()],
    [`Treated ${unit}`, treatedUnits.size.toLocaleString()],
    [`Control ${unit}`, controlUnits.size.toLocaleString()],
    ['Selected sats', activeSatSet().size]
  ]);
  updateEquation();
  drawDidMeans(rows, 'log_ntl', 'didMeansPlot');
  drawDidMeans(rows, 'stable_sum', 'didMeansRawPlot');
  if (!treatedUnits.size || !controlUnits.size) {
    for (const target of ['eventStudyPlot', 'eventStudyRawPlot']) {
      Plotly.react(target, [], { annotations: [{ text: `Need at least one treated and one control ${analysisUnitSingular()}.`, showarrow: false }] }, { displayModeBar: false });
    }
    document.getElementById('regressionTable').innerHTML = `<tr><td>Need at least one treated and one control ${analysisUnitSingular()}.</td></tr>`;
    document.getElementById('regressionTableRaw').innerHTML = `<tr><td>Need at least one treated and one control ${analysisUnitSingular()}.</td></tr>`;
    document.getElementById('regressionInterpretationLog').textContent = '';
    document.getElementById('regressionInterpretationRaw').textContent = '';
    return;
  }
  const fitLog = fitEventStudy(rows, 'log_ntl');
  const fitRaw = fitEventStudy(rows, 'stable_sum');
  renderEventStudy(fitLog, 'eventStudyPlot', 'log_ntl');
  renderEventStudy(fitRaw, 'eventStudyRawPlot', 'stable_sum');
  renderRegressionTable(fitLog, rows, treatedUnits.size, controlUnits.size, 'regressionTable', 'regressionInterpretationLog', 'log_ntl');
  renderRegressionTable(fitRaw, rows, treatedUnits.size, controlUnits.size, 'regressionTableRaw', 'regressionInterpretationRaw', 'stable_sum');
}
function groupMean(rows, treated, year, outcome) {
  const vals = rows.filter(r => r.treated === treated && r.year === year).map(r => r[outcome]);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
function activeFEGroups(rows) {
  const groups = [];
  if (controls.muniFE.checked) groups.push(rows.map(r => r.muni_key));
  if (controls.yearFE.checked) groups.push(rows.map(r => String(r.year)));
  if (controls.countryFE.checked) groups.push(rows.map(r => r.country_name));
  return groups;
}
function adjustedOutcomeRows(rows, outcome) {
  const groups = activeFEGroups(rows);
  if (!groups.length) return rows.map(r => ({ ...r, adjustedOutcome: r[outcome] }));
  const y = rows.map(r => r[outcome]);
  const centered = residualize(y, rows.map(() => []), groups).y;
  const ybar = mean(y);
  return rows.map((r, i) => ({ ...r, adjustedOutcome: centered[i] + ybar }));
}
function adjustedGroupMean(rows, treated, year) {
  const vals = rows.filter(r => r.treated === treated && r.year === year).map(r => r.adjustedOutcome);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
function drawDidMeans(rows, outcome, target) {
  const adjustedRows = adjustedOutcomeRows(rows, outcome);
  const tMean = YEARS.map(y => adjustedGroupMean(adjustedRows, true, y));
  const cMean = YEARS.map(y => adjustedGroupMean(adjustedRows, false, y));
  const logged = outcome === 'log_ntl';
  const adjusted = activeFEGroups(rows).length > 0;
  const label = adjusted ? 'adjusted' : 'actual';
  Plotly.react(target, [
    { type: 'scatter', mode: 'lines+markers', name: `Treated ${label}`, x: YEARS, y: tMean, line: { color: TREATED_COLOR } },
    { type: 'scatter', mode: 'lines+markers', name: `Control ${label}`, x: YEARS, y: cMean, line: { color: CONTROL_COLOR } }
  ], {
    title: { text: `${adjusted ? 'FE-adjusted' : 'Unadjusted'} mean ${logged ? 'log nightlights' : 'raw nightlights'}`, x: 0, font: { size: 12 } },
    margin: { l: 54, r: 16, t: 30, b: 38 },
    yaxis: { title: logged ? 'Mean log1p(NTL)' : 'Mean stable_sum' },
    shapes: impactYearShapes(),
    legend: { orientation: 'h', y: -0.22 }
  }, { displayModeBar: false, responsive: true });
}
function enforceFERules() {
  if (controls.muniFE.checked) {
    controls.countryFE.checked = false;
    controls.countryFE.disabled = true;
  } else {
    controls.countryFE.disabled = false;
  }
}
function updateEquation() {
  const sub = deathStateMode() ? 'st' : 'mt';
  const unitFe = deathStateMode() ? 'state FE' : 'municipality FE';
  const parts = [`Y_${sub} = alpha, where Y is either log(1 + NTL_${sub}) or raw NTL_${sub}`];
  if (!controls.muniFE.checked) parts.push('+ theta Treated');
  parts.push('+ sum_{y != 1997} delta_y (Treated x 1[year_t = y])');
  if (controls.muniFE.checked) parts.push(`+ ${unitFe}`);
  if (controls.yearFE.checked) parts.push('+ year FE');
  if (controls.countryFE.checked) parts.push('+ country FE');
  parts.push(`+ e_${sub}`);
  document.getElementById('equationText').textContent = parts.join(' ');
  document.getElementById('specAnswer').textContent = specAnswer();
}
function specAnswer() {
  const unit = analysisUnitPlural();
  const unitBase = deathStateMode() ? 'state baselines' : 'municipality baselines';
  if (deathStateMode()) {
    return 'Deaths-per-capita treatment is assigned at the state level, so municipality lights are summed to state-year observations before estimating the DiD.';
  }
  if (controls.muniFE.checked && controls.yearFE.checked) return `Across selected regional ${unit}, this estimates whether treated ${unit} changed differently after Mitch after removing ${unitBase} and common calendar-year shocks.`;
  if (controls.muniFE.checked) return `This estimates treated-year differences using within-${analysisUnitSingular()} changes, without removing common calendar-year shocks.`;
  if (controls.yearFE.checked && controls.countryFE.checked) return `This estimates treated-year differences net of permanent country differences and common year shocks, but not ${unitBase}.`;
  if (controls.yearFE.checked) return `This estimates treated-year differences net of common year shocks, but not permanent ${analysisUnitSingular()} differences.`;
  if (controls.countryFE.checked) return 'This estimates treated-year differences net of permanent country differences only.';
  return 'This is the least adjusted regional event-study contrast; it is descriptive and vulnerable to permanent place differences and common shocks.';
}

function fitEventStudy(rows, outcome) {
  const years = YEARS.filter(y => rows.some(r => r.year === y));
  const eventYears = years.filter(y => y !== REF_YEAR);
  const includeTreatMain = !controls.muniFE.checked;
  const names = [];
  if (includeTreatMain) names.push('treated_main');
  for (const y of eventYears) names.push(`tx_${y}`);
  let X = rows.map(r => {
    const row = [];
    if (includeTreatMain) row.push(r.treated ? 1 : 0);
    for (const y of eventYears) row.push(r.treated && r.year === y ? 1 : 0);
    return row;
  });
  let y = rows.map(r => r[outcome]);
  const groups = activeFEGroups(rows);
  let feDf = 0;
  for (const g of groups) feDf += Math.max(0, new Set(g).size - 1);
  if (!groups.length) {
    names.unshift('const');
    X = X.map(row => [1].concat(row));
  } else {
    const out = residualize(y, X, groups);
    y = out.y;
    X = out.X;
  }
  const keep = names.map((name, idx) => ({ name, idx, ss: X.reduce((s, row) => s + row[idx] * row[idx], 0) })).filter(d => d.ss > 1e-9);
  if (!keep.length) return { error: 'No estimable regressors for this selection.' };
  const keptNames = keep.map(d => d.name);
  const keptX = X.map(row => keep.map(d => row[d.idx]));
  const fit = ols(y, keptX);
  if (fit.error) return fit;
  const adjustedDf = Math.max(1, y.length - keptNames.length - feDf);
  if (adjustedDf !== fit.df) {
    const scale = Math.sqrt(fit.df / adjustedDf);
    fit.se = fit.se.map(v => v * scale);
    fit.df = adjustedDf;
  }
  const betaByName = new Map();
  const seByName = new Map();
  keptNames.forEach((name, i) => {
    betaByName.set(name, fit.beta[i]);
    seByName.set(name, fit.se[i]);
  });
  const coefs = eventYears.map(year => {
    const name = `tx_${year}`;
    const coef = betaByName.get(name);
    const se = seByName.get(name);
    return { year, coef: coef ?? null, se: se ?? null, t: se ? coef / se : null, primary: year === PRIMARY_YEAR, omitted: !betaByName.has(name) };
  });
  coefs.unshift({ year: REF_YEAR, coef: 0, se: 0, t: null, reference: true, primary: false });
  const k = keptNames.length;
  const yhat = keptX.map(row => row.reduce((s, v, i) => s + v * fit.beta[i], 0));
  const resid = y.map((v, i) => v - yhat[i]);
  const sse = resid.reduce((s, v) => s + v * v, 0);
  const ybar = y.reduce((s, v) => s + v, 0) / y.length;
  const tss = y.reduce((s, v) => s + (v - ybar) ** 2, 0);
  return { coefs, names: keptNames, n: rows.length, k, feDf, r2: tss ? 1 - sse / tss : null, df: fit.df, sse };
}
function residualize(yIn, XIn, groups) {
  let y = yIn.slice();
  let X = XIn.map(row => row.slice());
  const k = X[0]?.length || 0;
  for (let iter = 0; iter < 30; iter++) {
    let maxChange = 0;
    for (const group of groups) {
      const stats = new Map();
      for (let i = 0; i < y.length; i++) {
        const key = group[i];
        let rec = stats.get(key);
        if (!rec) {
          rec = { n: 0, sy: 0, sx: Array(k).fill(0) };
          stats.set(key, rec);
        }
        rec.n += 1;
        rec.sy += y[i];
        for (let j = 0; j < k; j++) rec.sx[j] += X[i][j];
      }
      for (let i = 0; i < y.length; i++) {
        const rec = stats.get(group[i]);
        const oldY = y[i];
        y[i] -= rec.sy / rec.n;
        maxChange = Math.max(maxChange, Math.abs(y[i] - oldY));
        for (let j = 0; j < k; j++) X[i][j] -= rec.sx[j] / rec.n;
      }
    }
    if (maxChange < 1e-8) break;
  }
  return { y, X };
}
function ols(y, X) {
  const n = y.length, k = X[0].length;
  const xtx = Array.from({ length: k }, () => Array(k).fill(0));
  const xty = Array(k).fill(0);
  for (let r = 0; r < n; r++) {
    for (let i = 0; i < k; i++) {
      xty[i] += X[r][i] * y[r];
      for (let j = 0; j < k; j++) xtx[i][j] += X[r][i] * X[r][j];
    }
  }
  const inv = inverse(xtx);
  if (!inv) return { error: 'Regression matrix is singular for the current sample and FE selection.' };
  const beta = inv.map(row => row.reduce((s, v, i) => s + v * xty[i], 0));
  const resid = y.map((v, r) => v - X[r].reduce((s, x, i) => s + x * beta[i], 0));
  const df = Math.max(1, n - k);
  const sigma2 = resid.reduce((s, v) => s + v * v, 0) / df;
  const se = inv.map((row, i) => Math.sqrt(Math.max(0, sigma2 * row[i])));
  return { beta, se, df };
}
function inverse(matrix) {
  const n = matrix.length;
  const a = matrix.map((row, i) => row.concat(Array.from({ length: n }, (_, j) => i === j ? 1 : 0)));
  for (let i = 0; i < n; i++) {
    let pivot = i;
    for (let r = i + 1; r < n; r++) if (Math.abs(a[r][i]) > Math.abs(a[pivot][i])) pivot = r;
    if (Math.abs(a[pivot][i]) < 1e-10) return null;
    [a[i], a[pivot]] = [a[pivot], a[i]];
    const div = a[i][i];
    for (let c = 0; c < 2 * n; c++) a[i][c] /= div;
    for (let r = 0; r < n; r++) {
      if (r === i) continue;
      const factor = a[r][i];
      for (let c = 0; c < 2 * n; c++) a[r][c] -= factor * a[i][c];
    }
  }
  return a.map(row => row.slice(n));
}
function stars(t) {
  const a = Math.abs(t || 0);
  if (a >= 2.576) return '***';
  if (a >= 1.96) return '**';
  if (a >= 1.645) return '*';
  return '';
}
function renderEventStudy(fit, target, outcome) {
  if (fit.error) {
    Plotly.react(target, [], { annotations: [{ text: fit.error, showarrow: false }] }, { displayModeBar: false });
    return;
  }
  const coefs = fit.coefs.filter(d => !d.omitted);
  const logged = outcome === 'log_ntl';
  Plotly.react(target, [{
    type: 'scatter',
    mode: 'lines+markers',
    name: 'Treated x year',
    x: coefs.map(d => d.year),
    y: coefs.map(d => d.coef),
    error_y: { type: 'data', array: coefs.map(d => d.se ? 1.96 * d.se : 0), visible: true },
    marker: { color: coefs.map(d => d.primary ? TREATED_COLOR : CONTROL_COLOR), size: coefs.map(d => d.primary ? 9 : 6) },
    line: { color: logged ? TREATED_COLOR : CONTROL_COLOR }
  }], {
    title: { text: logged ? 'Event study: log nightlights' : 'Event study: raw nightlights', x: 0, font: { size: 12 } },
    margin: { l: 54, r: 16, t: 30, b: 38 },
    yaxis: { title: logged ? 'Log interaction coefficient' : 'Raw NTL interaction coefficient' },
    shapes: impactYearShapes().concat([
      { type: 'line', x0: Math.min(...YEARS), x1: Math.max(...YEARS), y0: 0, y1: 0, line: { color: '#9ca3af' } }
    ])
  }, { displayModeBar: false, responsive: true });
}
function format1999Interpretation(fit, outcome) {
  if (fit.error) return '';
  const primary = fit.coefs.find(d => d.year === PRIMARY_YEAR && !d.omitted && !d.reference);
  if (!primary || primary.coef === null) return 'The 1999 interaction is not estimable for the current selection.';
  const unit = analysisUnitPlural();
  const unitBase = deathStateMode() ? 'state baselines' : 'municipality baselines';
  const feText = controls.muniFE.checked && controls.yearFE.checked
    ? `after removing ${unitBase} and common year shocks`
    : controls.muniFE.checked
      ? `after removing ${unitBase}`
      : controls.yearFE.checked
        ? 'after removing common year shocks'
        : 'without fixed-effect adjustment';
  if (outcome === 'log_ntl') {
    const pct = 100 * (Math.exp(primary.coef) - 1);
    const direction = pct < 0 ? 'below' : 'above';
    return `1999 interpretation: the coefficient ${fmt(primary.coef, 3)} means treated ${unit} were ${fmtPct(Math.abs(pct))} ${direction} controls in 1999 relative to the 1997 treated-control gap, ${feText}.`;
  }
  const direction = primary.coef < 0 ? 'below' : 'above';
  return `1999 interpretation: the coefficient ${fmt(primary.coef, 1)} means treated ${unit} were ${fmt(Math.abs(primary.coef), 1)} stable_sum units ${direction} controls in 1999 relative to the 1997 treated-control gap, ${feText}.`;
}
function renderRegressionTable(fit, rows, treatedN, controlN, target, interpretationTarget, outcome) {
  if (fit.error) {
    document.getElementById(target).innerHTML = `<tr><td>${escapeHtml(fit.error)}</td></tr>`;
    document.getElementById(interpretationTarget).textContent = '';
    return;
  }
  const logged = outcome === 'log_ntl';
  const body = fit.coefs.map(d => {
    const cls = d.primary ? ' class="primary"' : '';
    const label = d.reference ? `${d.year} (ref)` : d.omitted ? `${d.year} (omitted)` : String(d.year);
    if (logged) {
      const pct = d.coef === null ? null : 100 * (Math.exp(d.coef) - 1);
      return `<tr${cls}><td>${label}</td><td>${d.coef === null ? '' : fmt(d.coef, 3)}${d.t ? stars(d.t) : ''}</td><td>${pct === null ? '' : fmtPct(pct)}</td><td>${d.se === null ? '' : fmt(d.se, 3)}</td><td>${d.t === null ? '' : fmt(d.t, 2)}</td></tr>`;
    }
    return `<tr${cls}><td>${label}</td><td>${d.coef === null ? '' : fmt(d.coef, 1)}${d.t ? stars(d.t) : ''}</td><td>${d.se === null ? '' : fmt(d.se, 1)}</td><td>${d.t === null ? '' : fmt(d.t, 2)}</td></tr>`;
  }).join('');
  const unitLabel = analysisUnitPlural();
  const feChoices = `${controls.muniFE.checked ? `${deathStateMode() ? 'state' : 'municipality'} FE; ` : ''}${controls.yearFE.checked ? 'year FE; ' : ''}${controls.countryFE.checked ? 'country FE; ' : ''}${(!controls.muniFE.checked && !controls.yearFE.checked && !controls.countryFE.checked) ? 'none' : ''}`;
  if (logged) {
    document.getElementById(target).innerHTML =
      `<tr><th>Year interaction</th><th>Log coef.</th><th>% effect</th><th>SE</th><th>t</th></tr>${body}
      <tr><td>N</td><td>${fit.n.toLocaleString()}</td><td>R2</td><td>${fmt(fit.r2, 3)}</td><td></td></tr>
      <tr><td>Treated ${unitLabel}</td><td>${treatedN}</td><td>Control ${unitLabel}</td><td>${controlN}</td><td></td></tr>
      <tr><td>FE choices</td><td colspan="4">${feChoices}</td></tr>`;
  } else {
    document.getElementById(target).innerHTML =
      `<tr><th>Year interaction</th><th>Raw coef.</th><th>SE</th><th>t</th></tr>${body}
      <tr><td>N</td><td>${fit.n.toLocaleString()}</td><td>R2</td><td>${fmt(fit.r2, 3)}</td></tr>
      <tr><td>Treated ${unitLabel}</td><td>${treatedN}</td><td>Control ${unitLabel}</td><td>${controlN}</td></tr>
      <tr><td>FE choices</td><td colspan="3">${feChoices}</td></tr>`;
  }
  document.getElementById(interpretationTarget).textContent = format1999Interpretation(fit, outcome);
}

function updateMaps() {
  if (ntlMuniLayer) ntlMuniLayer.setStyle(ntlStyle);
  if (exposureMuniLayer) exposureMuniLayer.setStyle(exposureStyle);
  refreshYangParagLayer();
  if (document.getElementById('ntlTab').classList.contains('active')) refreshMap(ntlMap, ntlMuniLayer);
  if (document.getElementById('exposureTab').classList.contains('active')) refreshMap(exposureMap, exposureMuniLayer);
}
function updateAll() {
  computeActive();
  updateLabels();
  updateMaps();
  updateNTL();
  updateExposure();
  updateResults();
}

initControls();
computeActive();
initMaps();
updateAll();
</script>
</body>
</html>
"""


def build(output: Path) -> None:
    municipalities = read_json(WEB_DIR / "did_besttrack_chirps_municipalities.geojson")
    for feature in municipalities.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry")
        if geom:
            rep = shape(geom).representative_point()
            props["yang_rep_lat"] = rep.y
            props["yang_rep_lon"] = rep.x
    state_impacts = state_impact_records(municipalities)
    impact_by_state = {r["state_key"]: r for r in state_impacts if r.get("matched_dashboard_state")}
    for feature in municipalities.get("features", []):
        props = feature.get("properties", {})
        rec = impact_by_state.get(f"{props.get('country_name')}|{props.get('department_name')}", {})
        props["impact_population"] = rec.get("impact_population")
        props["impact_deaths"] = rec.get("impact_deaths")
        props["deaths_per_capita"] = rec.get("deaths_per_capita")
        props["impact_disappearances"] = rec.get("impact_disappearances")
        props["deaths_disappearances_per_capita"] = rec.get("deaths_disappearances_per_capita")
    matched_meta = {
        f["properties"]["muni_key"]: {
            "country_name": f["properties"].get("country_name"),
            "department_name": f["properties"].get("department_name"),
            "municipality_name": f["properties"].get("municipality_name"),
        }
        for f in municipalities["features"]
    }
    ntl_raw, ntl_manifest = ntl_records(matched_meta)
    yang_grid, _yang_geojson, yang_grid_meta = yang_parag_grid()
    manifest = read_json(DID_DIR / "manifest.json")
    if isinstance(manifest, dict):
        manifest = {**manifest, **ntl_manifest}
        manifest["yang_parag_grid_points"] = len(yang_grid)
        manifest["yang_parag_grid_geojson"] = str(YANG_PARAG_GRID_GEOJSON.as_posix())
        manifest.update(yang_grid_meta)
    payloads = {
        "__MUNICIPALITIES__": municipalities,
        "__STATE_IMPACTS__": state_impacts,
        "__NTL_RAW__": ntl_raw,
        "__TRACK_LINE__": read_json(PROCESSED_DIR / "mitch_track_line.geojson"),
        "__TRACK_POINTS__": read_json(PROCESSED_DIR / "mitch_track_points.geojson"),
        "__TRACK_ROWS__": csv_records(PROCESSED_DIR / "mitch_ibtracs_track.csv"),
        "__SWATHS__": {
            "r34": read_json(PROCESSED_DIR / "mitch_swath_r34.geojson"),
            "r50": read_json(PROCESSED_DIR / "mitch_swath_r50.geojson"),
            "r64": read_json(PROCESSED_DIR / "mitch_swath_r64.geojson"),
        },
        "__RAIN_OVERLAY__": rainfall_overlay(),
        "__YANG_PARAG_GRID__": yang_grid,
        "__MANIFEST__": manifest,
    }
    html = html_template()
    for token, payload in payloads.items():
        html = html.replace(token, safe_json(payload))
    output_path(output).write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build the integrated three-tab Mitch dashboard.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    build(args.output)
    print(f"Wrote dashboard: {output_path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
