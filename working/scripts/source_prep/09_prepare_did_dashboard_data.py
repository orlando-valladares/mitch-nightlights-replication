from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from shapely.geometry import LineString
from shapely.ops import unary_union

from pipeline_config import EXTERNAL_DIR, PROCESSED_DIR, RAW_DIR, WEB_DIR, WORKING_DIR, ensure_project_dirs, output_path
from pipeline_utils import to_numeric


ISO_TO_COUNTRY = {
    "BLZ": "Belize",
    "GTM": "Guatemala",
    "SLV": "El Salvador",
    "HND": "Honduras",
    "NIC": "Nicaragua",
    "CRI": "Costa Rica",
    "PAN": "Panama",
}
COUNTRY_TO_ISO = {v: k for k, v in ISO_TO_COUNTRY.items()}
DID_DIR = PROCESSED_DIR / "did_dashboard"


# Audited 1:1 name harmonization from the GAUL-coded NTL table to
# GeoBoundaries polygons. These are deliberately conservative: each alias is
# kept only when it points to one unique NTL unit and one unique polygon.
ADM1_MATCH_ALIASES: dict[tuple[str, str], str] = {
    ("HND", "islas de bahia"): "bay islands",
    ("HND", "paraiso"): "el paraiso",
    ("NIC", "atlantico norte"): "north carribean coast autonomous region",
    ("NIC", "atlantico sur"): "south atlantic autonomous region",
    ("NIC", "matagalpa"): "matagalpa departemento",
}

ADM2_MATCH_ALIASES: dict[tuple[str, str, str], str] = {
    ("HND", "comayagua", "ojo de agua"): "ojos de agua",
    ("HND", "copan", "cabanas"): "cabana",
    ("HND", "copan", "trinidad"): "trinidad de copan",
    ("HND", "lempira", "san manuel del colohete"): "san manuel colohete",
    ("HND", "ocotepeque", "nueva ocotepeque"): "ocotepeque",
    ("HND", "santa barbara", "san jose de colimas"): "san jose de colinas",
    ("NIC", "atlantico norte", "waspam"): "waspan",
    ("NIC", "atlantico sur", "bocanas de paiwa"): "el ayote",
    ("NIC", "chinandega", "cinco pinos"): "san juan de cinco pinos",
    ("NIC", "chinandega", "san fco del norte"): "san francisco del norte",
    ("NIC", "esteli", "plueblo nuevo"): "pueblo nuevo",
    ("NIC", "jinotega", "jinotega"): "de jinotega",
    ("NIC", "jinotega", "san sebastian de yali"): "muncipio san sebastian de yali",
    ("NIC", "jinotega", "wiwili"): "wiwili de jinotega",
    ("NIC", "leon", "malpaisillo"): "larreynaga",
    ("NIC", "madriz", "san juan del rio coco"): "san juan de rio coco",
    ("NIC", "madriz", "totolgalpa"): "totogalpa",
    ("NIC", "managua", "villa carlos fonseca a"): "villa el carmen",
    ("NIC", "masaya", "nandasmo"): "nandasmo muncipio",
    ("NIC", "matagalpa", "ciudad dario"): "ciudad darco",
    ("NIC", "matagalpa", "la dalia"): "el tuma la dalia",
    ("NIC", "nueva segovia", "dipilto"): "dipilito",
    ("NIC", "nueva segovia", "mosonte"): "monzonte",
    ("NIC", "rivas", "moyogalpa"): "moyagalpa muncipio",
    ("GTM", "alta verapaz", "raxruja"): "raxruha",
    ("GTM", "alta verapaz", "santa catarina la tinta"): "santa catalina la tinta",
    ("GTM", "chiquimula", "quetzaltepeque"): "quezaltepeque",
    ("GTM", "chiquimula", "san juan la ermita"): "san juan ermita",
    ("GTM", "el progreso", "san cristobal acasguastlan"): "san cristobal acasaguastlan",
    ("GTM", "escuintla", "santa lucia cotzulmalguapa"): "santa lucia cotzumalguapa",
    ("GTM", "guatemala", "san raymundo"): "san raimundo",
    ("GTM", "huehuetenango", "san idelfonso ixtahuacan"): "ixtahuacan",
    ("GTM", "quetzaltenango", "san juan ostuncalco"): "ostuncalco",
    ("GTM", "retalhuleu", "san felipe retalhuleu"): "san felipe",
    ("GTM", "solola", "san antonio palapo"): "san antonio palopo",
    ("GTM", "solola", "santa catarina palapo"): "santa catarina palopo",
    ("GTM", "suchitepequez", "san bernandino"): "san bernardino",
    ("GTM", "suchitepequez", "san pablo jocopila"): "san pablo jocopilas",
    ("GTM", "totonicapan", "san bartolo aguas calientes"): "san bartolo",
}

NON_1TO1_REASON_PATTERNS: list[tuple[str, str]] = [
    ("administrative unit not available", "No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon."),
    ("lago", "Water body / lake unit in the NTL source; GeoBoundaries municipality polygons do not contain a 1:1 lake municipality."),
    ("isla", "Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries."),
    ("islas", "Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries."),
]


def alias_adm1(iso: str, adm1_norm: str) -> str:
    return ADM1_MATCH_ALIASES.get((iso, adm1_norm), adm1_norm)


def alias_adm2(iso: str, adm1_norm: str, adm2_norm: str) -> str:
    return ADM2_MATCH_ALIASES.get((iso, adm1_norm, adm2_norm), adm2_norm)


def unmatched_reason(row: pd.Series) -> str:
    adm2_values = [
        str(row.get("adm2_norm", "")),
        str(row.get("match_adm2_norm", "")),
        norm_name(row.get("ADM2_NAME", "")),
    ]
    for pattern, reason in NON_1TO1_REASON_PATTERNS:
        if any(pattern in value for value in adm2_values):
            return reason
    if pd.notna(row.get("geo_match_count")) and row.get("geo_match_count") != 1:
        return "Alias is not accepted because it does not point to exactly one GeoBoundaries polygon."
    if pd.notna(row.get("ntl_match_count")) and row.get("ntl_match_count") != 1:
        return "Alias is not accepted because multiple NTL units would map to the same polygon."
    return "No conservative 1:1 polygon match found in GeoBoundaries after audited aliases."


def norm_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    replacements = [
        r"\bmunicipio\b",
        r"\bcanton de\b",
        r"\bcanton\b",
        r"\bprovincia de\b",
        r"\bprovincia\b",
        r"\bdepartamento de\b",
        r"\bdepartamento\b",
        r"\bdistrict\b",
        r"\bprovince\b",
        r"\bcomarca\b",
    ]
    for pattern in replacements:
        text = re.sub(pattern, " ", text)
    text = text.replace("kuna", "guna")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def gaul_key(df: pd.DataFrame) -> pd.Series:
    return (
        to_numeric(df["ADM0_CODE"]).astype("Int64").astype(str)
        + "_"
        + to_numeric(df["ADM1_CODE"]).astype("Int64").astype(str)
        + "_"
        + to_numeric(df["ADM2_CODE"]).astype("Int64").astype(str)
    )


def read_ntl_units(ntl_path: Path) -> pd.DataFrame:
    cols = ["ADM0_NAME", "ADM1_NAME", "ADM2_NAME", "ADM0_CODE", "ADM1_CODE", "ADM2_CODE"]
    ntl = pd.read_csv(ntl_path, usecols=cols).drop_duplicates().reset_index(drop=True)
    ntl["muni_key"] = gaul_key(ntl)
    ntl["iso"] = ntl["ADM0_NAME"].map(COUNTRY_TO_ISO)
    ntl["adm1_norm"] = ntl["ADM1_NAME"].map(norm_name)
    ntl["adm2_norm"] = ntl["ADM2_NAME"].map(norm_name)
    belize = ntl["ADM0_NAME"].eq("Belize")
    ntl.loc[belize, "adm2_norm"] = ntl.loc[belize, "ADM1_NAME"].map(norm_name)
    ntl["match_adm1_norm"] = [alias_adm1(row.iso, row.adm1_norm) for row in ntl.itertuples()]
    ntl["match_adm2_norm"] = [alias_adm2(row.iso, row.adm1_norm, row.adm2_norm) for row in ntl.itertuples()]
    ntl["adm1_alias_applied"] = ntl["match_adm1_norm"].ne(ntl["adm1_norm"])
    ntl["adm2_alias_applied"] = ntl["match_adm2_norm"].ne(ntl["adm2_norm"])
    return ntl


def geoboundaries_features() -> gpd.GeoDataFrame:
    frames: list[gpd.GeoDataFrame] = []
    for iso in ISO_TO_COUNTRY:
        adm2_path = EXTERNAL_DIR / f"geoboundaries_adm2_{iso}.geojson"
        adm1_path = EXTERNAL_DIR / f"geoboundaries_adm1_{iso}.geojson"
        if not adm2_path.exists() or not adm1_path.exists():
            raise FileNotFoundError(f"Missing GeoBoundaries ADM1/ADM2 files for {iso}.")
        adm2 = gpd.read_file(adm2_path).to_crs("EPSG:4326")
        adm1 = gpd.read_file(adm1_path).to_crs("EPSG:4326")
        adm2["rep_point"] = adm2.geometry.representative_point()
        pts = gpd.GeoDataFrame(adm2.drop(columns="geometry"), geometry="rep_point", crs="EPSG:4326")
        joined = gpd.sjoin(
            pts,
            adm1[["shapeName", "geometry"]],
            how="left",
            predicate="within",
            lsuffix="adm2",
            rsuffix="adm1",
        )
        adm1_col = "shapeName_adm1" if "shapeName_adm1" in joined.columns else "shapeName_right"
        adm2["adm1_geo"] = joined[adm1_col].to_numpy()
        adm2["iso"] = iso
        adm2["source_level"] = "GeoBoundaries ADM2"
        adm2["adm1_norm"] = adm2["adm1_geo"].map(norm_name)
        adm2["adm2_norm"] = adm2["shapeName"].map(norm_name)
        adm2["match_adm1_norm"] = adm2["adm1_norm"]
        adm2["match_adm2_norm"] = adm2["adm2_norm"]
        adm2 = adm2.rename(columns={"shapeName": "adm2_geo", "shapeID": "geometry_source_id"})
        frames.append(adm2[["iso", "adm1_geo", "adm2_geo", "adm1_norm", "adm2_norm", "match_adm1_norm", "match_adm2_norm", "geometry_source_id", "source_level", "geometry"]])

        if iso == "BLZ":
            belize = adm1.copy()
            belize["iso"] = iso
            belize["adm1_geo"] = belize["shapeName"]
            belize["adm2_geo"] = belize["shapeName"]
            belize["adm1_norm"] = belize["shapeName"].map(norm_name)
            belize["adm2_norm"] = belize["shapeName"].map(norm_name)
            belize["match_adm1_norm"] = belize["adm1_norm"]
            belize["match_adm2_norm"] = belize["adm2_norm"]
            belize["geometry_source_id"] = "ADM1_" + belize["shapeID"].astype(str)
            belize["source_level"] = "GeoBoundaries ADM1 dissolved for GAUL Belize units"
            frames.append(
                belize[["iso", "adm1_geo", "adm2_geo", "adm1_norm", "adm2_norm", "match_adm1_norm", "match_adm2_norm", "geometry_source_id", "source_level", "geometry"]]
            )
    out = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")


def build_gaul_name_matched_boundaries(ntl_units: pd.DataFrame) -> tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]:
    geo = geoboundaries_features()
    keys = ["iso", "match_adm1_norm", "match_adm2_norm"]
    geo_counts = geo.groupby(keys).size().rename("geo_match_count").reset_index()
    ntl_counts = ntl_units.groupby(keys).size().rename("ntl_match_count").reset_index()
    geo_unique = geo.merge(geo_counts, on=keys, how="left")
    joined = ntl_units.merge(geo_unique, on=keys, how="left").merge(ntl_counts, on=keys, how="left")
    matched_mask = joined["geometry_source_id"].notna() & joined["geo_match_count"].eq(1) & joined["ntl_match_count"].eq(1)
    joined["match_status"] = np.where(matched_mask, "matched", "unmatched")
    joined["match_method"] = np.where(
        matched_mask & (joined["adm1_alias_applied"] | joined["adm2_alias_applied"]),
        "audited 1:1 alias",
        np.where(matched_mask, "exact normalized country+ADM1+ADM2 name", "unmatched"),
    )
    joined["unmatched_reason"] = ""
    unmatched = joined["match_status"].eq("unmatched")
    joined.loc[unmatched, "unmatched_reason"] = joined.loc[unmatched].apply(unmatched_reason, axis=1)
    exact = joined.loc[matched_mask].copy()
    exact["country_name"] = exact["ADM0_NAME"]
    exact["department_name"] = exact["ADM1_NAME"]
    exact["municipality_name"] = exact["ADM2_NAME"]
    exact["match_method"] = exact["match_method"].where(
        ~exact["country_name"].eq("Belize"),
        exact["match_method"] + "; Belize uses ADM1 geometry for GAUL unavailable ADM2",
    )
    gdf = gpd.GeoDataFrame(exact, geometry="geometry", crs="EPSG:4326")
    keep = [
        "muni_key",
        "ADM0_CODE",
        "ADM1_CODE",
        "ADM2_CODE",
        "country_name",
        "department_name",
        "municipality_name",
        "geometry_source_id",
        "source_level",
        "match_method",
        "adm1_geo",
        "adm2_geo",
        "adm1_alias_applied",
        "adm2_alias_applied",
        "geometry",
    ]
    gdf = gdf[keep].reset_index(drop=True)

    coverage = pd.DataFrame(
        [
            {
                "metric": "ntl_municipalities",
                "value": int(ntl_units["muni_key"].nunique()),
            },
            {
                "metric": "exact_name_matched_municipalities",
                "value": int(gdf["muni_key"].nunique()),
            },
            {
                "metric": "unmatched_municipalities",
                "value": int(ntl_units["muni_key"].nunique() - gdf["muni_key"].nunique()),
            },
        ]
    )
    by_country = ntl_units.groupby("ADM0_NAME")["muni_key"].nunique().rename("ntl_municipalities").reset_index()
    matched = gdf.groupby("country_name")["muni_key"].nunique().rename("matched_municipalities").reset_index()
    by_country = by_country.merge(matched, left_on="ADM0_NAME", right_on="country_name", how="left")
    by_country["matched_municipalities"] = by_country["matched_municipalities"].fillna(0).astype(int)
    by_country["unmatched_municipalities"] = by_country["ntl_municipalities"] - by_country["matched_municipalities"]
    by_country = by_country.drop(columns=["country_name"])
    registry_cols = ["muni_key", "ADM0_NAME", "ADM1_NAME", "ADM2_NAME", "ADM0_CODE", "ADM1_CODE", "ADM2_CODE", "adm1_norm", "adm2_norm", "match_adm1_norm", "match_adm2_norm", "adm1_alias_applied", "adm2_alias_applied", "adm1_geo", "adm2_geo", "geometry_source_id", "geo_match_count", "ntl_match_count", "match_status", "match_method", "unmatched_reason"]
    registry = joined[[c for c in registry_cols if c in joined.columns]].drop_duplicates(subset=["muni_key"]).reset_index(drop=True)
    return gdf, pd.concat([coverage, by_country.rename(columns={"ADM0_NAME": "metric", "ntl_municipalities": "value"})], ignore_index=True), registry



def write_boundary_registry_md(registry: pd.DataFrame, coverage: pd.DataFrame) -> None:
    matched = int(registry["match_status"].eq("matched").sum())
    unmatched = int(registry["match_status"].eq("unmatched").sum())
    alias_matched = int((registry["match_status"].eq("matched") & (registry["adm1_alias_applied"] | registry["adm2_alias_applied"])).sum())
    lines = [
        "# Municipality Boundary Match Registry",
        "",
        "This registry documents the audited 1:1 corrections from GAUL-coded NTL municipalities to GeoBoundaries polygons.",
        "Raw source files remain unchanged under `raw/`; corrected working outputs are rebuilt under `working/` and `out/`.",
        "",
        "## Summary",
        f"- NTL municipality units: {len(registry):,}",
        f"- Matched to one polygon: {matched:,}",
        f"- Matched through audited aliases: {alias_matched:,}",
        f"- Still unmatched: {unmatched:,}",
        "",
        "## Match Policy",
        "- Exact normalized country + ADM1 + ADM2 matches are retained.",
        "- Audited aliases are retained only when one NTL unit maps to exactly one GeoBoundaries polygon.",
        "- Placeholder, lake, island-fragment, and many-to-one cases are not forced into a polygon.",
        "",
        "## Country Coverage",
        "| Country/metric | NTL units | Matched | Unmatched |",
        "|---|---:|---:|---:|",
    ]
    for _, row in coverage.iterrows():
        metric = str(row.get("metric", ""))
        if metric in {"ntl_municipalities", "exact_name_matched_municipalities", "unmatched_municipalities"}:
            continue
        lines.append(f"| {metric} | {int(row.get('value', 0)):,} | {int(row.get('matched_municipalities', 0)):,} | {int(row.get('unmatched_municipalities', 0)):,} |")
    lines.extend(["", "## Audited Alias Matches", "| Country | Source ADM1 | Source ADM2 | Polygon ADM1 | Polygon ADM2 | Alias Type |", "|---|---|---|---|---|---|"])
    alias_rows = registry.loc[registry["match_status"].eq("matched") & (registry["adm1_alias_applied"] | registry["adm2_alias_applied"])].copy()
    for _, row in alias_rows.sort_values(["ADM0_NAME", "ADM1_NAME", "ADM2_NAME"]).iterrows():
        alias_type = ", ".join(label for label, flag in [("ADM1", row.get("adm1_alias_applied")), ("ADM2", row.get("adm2_alias_applied"))] if bool(flag))
        lines.append(f"| {row['ADM0_NAME']} | {row['ADM1_NAME']} | {row['ADM2_NAME']} | {row.get('adm1_geo', '')} | {row.get('adm2_geo', '')} | {alias_type} |")
    lines.extend(["", "## Still Unmatched / Not Forced", "| Country | ADM1 | ADM2 | Reason |", "|---|---|---|---|"])
    unresolved = registry.loc[registry["match_status"].eq("unmatched")].copy()
    for _, row in unresolved.sort_values(["ADM0_NAME", "ADM1_NAME", "ADM2_NAME"]).iterrows():
        lines.append(f"| {row['ADM0_NAME']} | {row['ADM1_NAME']} | {row['ADM2_NAME']} | {row.get('unmatched_reason', '')} |")
    output_path(WORKING_DIR / "municipality_boundary_match_registry.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

def load_track(track_path: Path) -> pd.DataFrame:
    track = pd.read_csv(track_path)
    track["iso_time"] = pd.to_datetime(track["iso_time"], utc=True, errors="coerce")
    track["lat"] = to_numeric(track["lat"])
    track["lon"] = to_numeric(track["lon"])
    track["wind_kt"] = to_numeric(track["wind_kt"])
    track["pressure_mb"] = to_numeric(track["pressure_mb"])
    return track.dropna(subset=["iso_time", "lat", "lon"]).sort_values("iso_time").reset_index(drop=True)


def metric_crs(gdf: gpd.GeoDataFrame) -> str:
    crs = gdf.estimate_utm_crs()
    return crs.to_string() if crs is not None else "EPSG:32616"


def distance_exposure(boundaries: gpd.GeoDataFrame, track: pd.DataFrame) -> pd.DataFrame:
    t_gdf = gpd.GeoDataFrame(track, geometry=gpd.points_from_xy(track["lon"], track["lat"]), crs="EPSG:4326")
    crs = metric_crs(boundaries)
    b = boundaries.to_crs(crs)
    t = t_gdf.to_crs(crs)
    line = LineString(list(t.geometry))
    points = list(t.geometry)
    winds = track["wind_kt"].to_numpy(dtype=float)
    pressures = track["pressure_mb"].to_numpy(dtype=float)
    times = track["iso_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy()
    rows = []
    for idx, geom in enumerate(b.geometry):
        centroid = geom.centroid
        dists = np.array([centroid.distance(point) / 1000.0 for point in points], dtype=float)
        nearest_idx = int(np.nanargmin(dists))
        row = {
            "muni_key": boundaries.loc[idx, "muni_key"],
            "min_distance_to_track_km": round(float(geom.distance(line) / 1000.0), 3),
            "centroid_min_distance_to_track_km": round(float(np.nanmin(dists)), 3),
            "nearest_track_time": times[nearest_idx],
            "nearest_track_wind_kt": winds[nearest_idx],
            "nearest_track_pressure_mb": pressures[nearest_idx],
        }
        for km in [50, 100, 150, 200]:
            mask = dists <= km
            row[f"max_track_wind_within_{km}km"] = float(np.nanmax(winds[mask])) if mask.any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def swath_exposure(boundaries: gpd.GeoDataFrame) -> pd.DataFrame:
    area_crs = "EPSG:6933"
    b = boundaries.to_crs(area_crs)
    areas = b.geometry.area.replace(0, np.nan)
    out = pd.DataFrame({"muni_key": boundaries["muni_key"]})
    for threshold in ["r34", "r50", "r64"]:
        path = PROCESSED_DIR / f"mitch_swath_{threshold}.geojson"
        if not path.exists():
            shares = pd.Series(0.0, index=boundaries.index)
        else:
            swath = gpd.read_file(path).to_crs(area_crs)
            geom = unary_union(swath.geometry) if len(swath) else None
            shares = b.geometry.intersection(geom).area / areas if geom is not None else pd.Series(0.0, index=boundaries.index)
            shares = shares.fillna(0.0).clip(0, 1)
        out[f"share_area_{threshold}"] = shares.round(6)
        out[f"any_{threshold}"] = shares.gt(0).astype(int)
    out["max_swath_category"] = "none"
    out.loc[out["any_r34"].eq(1), "max_swath_category"] = "r34"
    out.loc[out["any_r50"].eq(1), "max_swath_category"] = "r50"
    out.loc[out["any_r64"].eq(1), "max_swath_category"] = "r64"
    return out


def band_stack(path: Path, geometry, crs) -> tuple[np.ndarray, np.ndarray]:
    with rasterio.open(path) as src:
        geom = gpd.GeoSeries([geometry], crs=crs).to_crs(src.crs).iloc[0]
        arr, _ = mask(src, [geom], crop=True, filled=False)
        data = arr.filled(np.nan) if np.ma.isMaskedArray(arr) else arr.astype(float)
    return data.astype(float), np.isfinite(data).all(axis=0)


def rainfall_exposure(boundaries: gpd.GeoDataFrame, mitch_path: Path, clim_path: Path) -> pd.DataFrame:
    rows = []
    for _, muni in boundaries.iterrows():
        try:
            mitch, _ = band_stack(mitch_path, muni.geometry, boundaries.crs)
            clim, _ = band_stack(clim_path, muni.geometry, boundaries.crs)
        except ValueError:
            mitch = clim = np.empty((0, 0, 0), dtype=float)
        if mitch.size == 0 or clim.size == 0:
            vals = {}
        else:
            valid = np.isfinite(mitch).all(axis=0) & np.isfinite(clim).all(axis=0)
            m_total = np.nansum(mitch, axis=0)
            c_total = np.nansum(clim, axis=0)
            m_max = np.nanmax(mitch, axis=0)
            c_max = np.nanmax(clim, axis=0)
            vals = {
                "rain_total_mean_mm": ("mean", m_total[valid]),
                "rain_total_max_pixel_mm": ("max", m_total[valid]),
                "rain_total_anomaly_mm": ("mean", (m_total - c_total)[valid]),
                "rain_max_daily_mean_mm": ("mean", m_max[valid]),
                "rain_max_daily_max_pixel_mm": ("max", m_max[valid]),
                "rain_max_daily_anomaly_mm": ("mean", (m_max - c_max)[valid]),
            }
        row = {"muni_key": muni["muni_key"]}
        for key, (stat, arr) in vals.items():
            if not len(arr):
                row[key] = np.nan
            elif stat == "max":
                row[key] = float(np.nanmax(arr))
            else:
                row[key] = float(np.nanmean(arr))
        row["rain_pixel_count"] = int(len(next(iter(vals.values()))[1])) if vals else 0
        rows.append(row)
    return pd.DataFrame(rows)


def ntl_panel(ntl_path: Path, matched_keys: set[str]) -> pd.DataFrame:
    usecols = ["ADM0_NAME", "ADM1_NAME", "ADM2_NAME", "ADM0_CODE", "ADM1_CODE", "ADM2_CODE", "year", "satellite", "stable_sum"]
    ntl = pd.read_csv(ntl_path, usecols=usecols)
    ntl["muni_key"] = gaul_key(ntl)
    ntl = ntl[ntl["muni_key"].isin(matched_keys)].copy()
    ntl["stable_sum"] = to_numeric(ntl["stable_sum"])
    ntl["year"] = to_numeric(ntl["year"]).astype(int)
    panel = ntl.groupby(["muni_key", "year"], as_index=False)["stable_sum"].mean()
    pre = panel[panel["year"] <= 1998].groupby("muni_key")["stable_sum"].mean().rename("pre_mean_stable_sum").reset_index()
    return panel.merge(pre, on="muni_key", how="left")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare GAUL-coded data for the expanded BestTrack/CHIRPS DiD dashboard.")
    parser.add_argument("--ntl", type=Path, default=RAW_DIR / "dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv")
    parser.add_argument("--mitch-rain", type=Path, default=RAW_DIR / "chirps_mitch_daily_stack_19981027_19981104_ca5.tif")
    parser.add_argument("--clim-rain", type=Path, default=RAW_DIR / "chirps_climatology_stack_1981_present_oct27_nov04_ca5.tif")
    parser.add_argument("--simplify-meters", type=float, default=500.0)
    args = parser.parse_args(argv)

    ensure_project_dirs()
    output_path(DID_DIR / "placeholder.txt").unlink(missing_ok=True)
    DID_DIR.mkdir(parents=True, exist_ok=True)

    ntl_units = read_ntl_units(args.ntl)
    boundaries, coverage, registry = build_gaul_name_matched_boundaries(ntl_units)
    if boundaries.empty:
        blocker = DID_DIR / "GAUL_BOUNDARY_BLOCKER.txt"
        output_path(blocker).write_text(
            "No GAUL-coded municipality geometries could be matched. Raw GAUL shapefile lacks sidecars and exact boundary data was unavailable.\n",
            encoding="utf-8",
        )
        raise RuntimeError(f"GAUL boundary blocker written to {blocker}")

    track = load_track(PROCESSED_DIR / "mitch_ibtracs_track.csv")
    exposure = boundaries.drop(columns=[c for c in ["geometry"] if c in boundaries.columns]).copy()
    for df in [
        distance_exposure(boundaries, track),
        swath_exposure(boundaries),
        rainfall_exposure(boundaries, args.mitch_rain, args.clim_rain),
    ]:
        exposure = exposure.merge(df, on="muni_key", how="left")

    gdf = boundaries.merge(exposure.drop(columns=[c for c in boundaries.columns if c != "muni_key"], errors="ignore"), on="muni_key", how="left")
    gdf.to_file(output_path(DID_DIR / "gaul_name_matched_municipalities_analytical.geojson"), driver="GeoJSON")
    exposure.to_csv(output_path(DID_DIR / "gaul_name_matched_exposure.csv"), index=False)
    coverage.to_csv(output_path(DID_DIR / "gaul_name_match_coverage.csv"), index=False)
    registry.to_csv(output_path(DID_DIR / "gaul_boundary_match_registry.csv"), index=False)
    registry.to_csv(output_path(WORKING_DIR / "municipality_boundary_match_registry.csv"), index=False)
    write_boundary_registry_md(registry, coverage)

    panel = ntl_panel(args.ntl, set(boundaries["muni_key"]))
    panel.to_csv(output_path(DID_DIR / "ntl_municipality_year_panel.csv"), index=False)

    web_gdf = gdf.to_crs("EPSG:3857")
    web_gdf["geometry"] = web_gdf.geometry.simplify(args.simplify_meters, preserve_topology=True)
    web_gdf = web_gdf.to_crs("EPSG:4326")
    web_gdf.to_file(output_path(WEB_DIR / "did_besttrack_chirps_municipalities.geojson"), driver="GeoJSON")

    manifest = {
        "matched_municipalities": int(boundaries["muni_key"].nunique()),
        "ntl_municipalities": int(ntl_units["muni_key"].nunique()),
        "match_policy": "Exact normalized country+ADM1+ADM2 names plus audited 1:1 aliases. Ambiguous, placeholder, island-fragment, lake, and unresolved names are excluded rather than forced.",
        "alias_matched_municipalities": int((registry["match_status"].eq("matched") & (registry["adm1_alias_applied"] | registry["adm2_alias_applied"])).sum()),
        "unmatched_municipalities_after_aliases": int(registry["match_status"].eq("unmatched").sum()),
        "belize_policy": "Belize GAUL units have ADM2_NAME='Administrative unit not available'; GeoBoundaries ADM1 geometries are used.",
    }
    output_path(DID_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
