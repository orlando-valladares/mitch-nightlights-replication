from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = ROOT / "working" / "data" / "processed"
OUT_PATH = ROOT / "out" / "besttrack_extended_dashboard.html"
AREA_CRS = "EPSG:6933"
GEOD = Geod(ellps="WGS84")
THRESHOLDS = ["r30", "r34", "r50", "r64"]
OFFICIAL_THRESHOLDS = {"r34", "r50", "r64"}
QUADRANTS = ["ne", "se", "sw", "nw"]
COUNTRY_LABELS = {
    "BLZ": "Belize",
    "CRI": "Costa Rica",
    "GTM": "Guatemala",
    "HND": "Honduras",
    "NIC": "Nicaragua",
    "PAN": "Panama",
    "SLV": "El Salvador",
}


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


def sector_polygon(lon: float, lat: float, radius_nm: float, quadrant: str) -> Polygon | None:
    if pd.isna(radius_nm) or radius_nm <= 0:
        return None
    starts = {"ne": 0.0, "se": 90.0, "sw": 180.0, "nw": 270.0}
    start = starts[quadrant]
    bearings = np.linspace(start, start + 90.0, 22)
    arc = []
    for bearing in bearings:
        x, y, _ = GEOD.fwd(float(lon), float(lat), float(bearing), float(radius_nm) * 1852.0)
        arc.append((x, y))
    poly = Polygon([(float(lon), float(lat)), *arc, (float(lon), float(lat))])
    return poly if poly.is_valid and not poly.is_empty else None


def load_ebtrk() -> pd.DataFrame:
    path = PROCESSED_DIR / "mitch_ebtrk_wind_radii.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run 04_build_wind_swaths.py first.")
    df = pd.read_csv(path)
    df["iso_time"] = pd.to_datetime(df["iso_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["iso_time", "lat", "lon"]).sort_values("iso_time").reset_index(drop=True)
    df = add_estimated_r30(df)
    return df


def estimate_r30_radius(vmax: float, rmw: float, r34: float, roci: float) -> float:
    if pd.isna(vmax) or vmax < 30:
        return 0.0
    rmw_valid = pd.notna(rmw) and rmw > 0
    r34_valid = pd.notna(r34) and r34 > 0
    roci_valid = pd.notna(roci) and roci > 0
    estimate = np.nan
    if r34_valid and rmw_valid and r34 > rmw and vmax > 34:
        estimate = rmw + ((30.0 - vmax) / (34.0 - vmax)) * (r34 - rmw)
    elif r34_valid:
        estimate = r34
    elif roci_valid:
        estimate = roci
    elif rmw_valid:
        estimate = rmw
    if pd.isna(estimate):
        return 0.0
    if r34_valid:
        estimate = max(float(estimate), float(r34))
    if roci_valid and (not r34_valid or roci >= r34):
        estimate = min(float(estimate), float(roci))
    return float(max(estimate, 0.0))


def add_estimated_r30(ebtrk: pd.DataFrame) -> pd.DataFrame:
    out = ebtrk.copy()
    for quadrant in QUADRANTS:
        out[f"r30_{quadrant}_nm"] = [
            estimate_r30_radius(row.vmax_kt, row.rmw_nm, getattr(row, f"r34_{quadrant}_nm"), row.roci_nm)
            for row in out.itertuples(index=False)
        ]
    return out


def load_municipalities() -> gpd.GeoDataFrame:
    path = PROCESSED_DIR / "municipalities_adm2_analytical.geojson"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}.")
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    keep = [c for c in ["muni_key", "country_name", "department_name", "municipality_name"] if c in gdf.columns]
    gdf = gdf[keep + ["geometry"]].copy()
    if "country_name" in gdf.columns:
        gdf["country_display"] = gdf["country_name"].map(COUNTRY_LABELS).fillna(gdf["country_name"])
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)


def build_swath_layers(ebtrk: pd.DataFrame) -> tuple[dict[str, object], dict[tuple[str, str], object]]:
    features = []
    swath_geoms: dict[tuple[str, str], object] = {}
    for threshold in THRESHOLDS:
        for quadrant in QUADRANTS:
            pieces = []
            col = f"{threshold}_{quadrant}_nm"
            positive = pd.to_numeric(ebtrk[col], errors="coerce").fillna(0)
            for _, row in ebtrk.loc[positive.gt(0)].iterrows():
                geom = sector_polygon(row["lon"], row["lat"], row[col], quadrant)
                if geom is not None:
                    pieces.append(geom)
            if not pieces:
                continue
            unioned = unary_union(pieces)
            swath_geoms[(threshold, quadrant)] = unioned
            display_geom = unioned.simplify(0.01, preserve_topology=True)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "threshold": threshold,
                        "threshold_kt": int(threshold[1:]),
                        "source_note": "Official EBTRK wind radius"
                        if threshold in OFFICIAL_THRESHOLDS
                        else "Estimated from EBTRK Vmax, RMW, 34 kt radii, and ROCI",
                        "quadrant": quadrant.upper(),
                        "records_with_radius": int(positive.gt(0).sum()),
                        "max_radius_nm": float(positive.max()),
                    },
                    "geometry": json.loads(gpd.GeoSeries([display_geom], crs="EPSG:4326").to_json())["features"][0]["geometry"],
                }
            )
    return {"type": "FeatureCollection", "features": features}, swath_geoms


def add_exposure_properties(munis: gpd.GeoDataFrame, swath_geoms: dict[tuple[str, str], object]) -> gpd.GeoDataFrame:
    out = munis.copy()
    metric = out.to_crs(AREA_CRS)
    areas = metric.geometry.area.replace(0, np.nan)
    for threshold in THRESHOLDS:
        threshold_cols = []
        for quadrant in QUADRANTS:
            col = f"share_{threshold}_{quadrant}"
            geom = swath_geoms.get((threshold, quadrant))
            if geom is None:
                out[col] = 0.0
            else:
                swath = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(AREA_CRS).iloc[0]
                shares = metric.geometry.intersection(swath).area / areas
                out[col] = shares.fillna(0).clip(0, 1).round(6)
            threshold_cols.append(col)
        out[f"any_{threshold}"] = out[threshold_cols].gt(0).any(axis=1).astype(int)
    return out


def municipality_geojson(munis: gpd.GeoDataFrame) -> dict[str, object]:
    display = munis.copy()
    display["geometry"] = display.geometry.simplify(0.004, preserve_topology=True)
    return json.loads(display.to_json())


def track_geojson(ebtrk: pd.DataFrame) -> tuple[dict[str, object], dict[str, object]]:
    points = gpd.GeoDataFrame(
        ebtrk.assign(iso_time=ebtrk["iso_time"].dt.strftime("%Y-%m-%d %H:%M UTC")),
        geometry=gpd.points_from_xy(ebtrk["lon"], ebtrk["lat"]),
        crs="EPSG:4326",
    )
    keep_cols = [
        "iso_time",
        "lat",
        "lon",
        "vmax_kt",
        "pressure_mb",
        "rmw_nm",
        "roci_nm",
        "storm_type",
        "distance_to_land_km",
        *[f"{t}_{q}_nm" for t in THRESHOLDS for q in QUADRANTS],
        "geometry",
    ]
    points = points[[c for c in keep_cols if c in points.columns]]
    line = gpd.GeoDataFrame(
        [{"storm": "MITCH", "source": "Extended Best Track"}],
        geometry=[LineString(zip(ebtrk["lon"], ebtrk["lat"]))],
        crs="EPSG:4326",
    )
    return json.loads(points.to_json()), json.loads(line.to_json())


def records_for_js(ebtrk: pd.DataFrame) -> list[dict[str, object]]:
    cols = [
        "iso_time",
        "lat",
        "lon",
        "vmax_kt",
        "pressure_mb",
        "rmw_nm",
        "roci_nm",
        "storm_type",
        "distance_to_land_km",
        *[f"{t}_{q}_nm" for t in THRESHOLDS for q in QUADRANTS],
    ]
    out = ebtrk[[c for c in cols if c in ebtrk.columns]].copy()
    out["iso_time"] = out["iso_time"].dt.strftime("%Y-%m-%d %H:%M UTC")
    return out.astype(object).where(pd.notna(out), None).to_dict(orient="records")


def summary_records(munis: gpd.GeoDataFrame) -> list[dict[str, object]]:
    rows = []
    for threshold in THRESHOLDS:
        cols = [f"share_{threshold}_{q}" for q in QUADRANTS]
        rows.append(
            {
                "threshold": threshold,
                "threshold_kt": int(threshold[1:]),
                "municipalities_any": int(munis[cols].gt(0).any(axis=1).sum()),
                "municipalities_50pct": int((munis[cols].max(axis=1) >= 0.5).sum()),
            }
        )
        for quadrant in QUADRANTS:
            col = f"share_{threshold}_{quadrant}"
            rows.append(
                {
                    "threshold": threshold,
                    "threshold_kt": int(threshold[1:]),
                    "quadrant": quadrant.upper(),
                    "municipalities_any": int(munis[col].gt(0).sum()),
                    "municipalities_50pct": int(munis[col].ge(0.5).sum()),
                }
            )
    return rows


def render_html(payload: dict[str, object]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hurricane Mitch Extended Best Track Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{ --ink:#17202a; --muted:#667085; --line:#dce3ec; --page:#f5f7fb; --panel:#fff; --red:#b91c1c; --teal:#0f766e; --amber:#d97706; --blue:#2563eb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; letter-spacing:0; }}
header {{ display:flex; justify-content:space-between; gap:18px; padding:16px 20px; background:#fff; border-bottom:1px solid var(--line); }}
h1 {{ margin:0; font-size:23px; }}
.sub {{ margin:4px 0 0; color:var(--muted); font-size:13px; max-width:920px; }}
main {{ padding:14px; }}
.layout {{ display:grid; grid-template-columns:360px minmax(0,1fr); gap:14px; align-items:start; }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
.pad {{ padding:14px; }}
h2 {{ margin:0 0 10px; font-size:16px; }}
h3 {{ margin:14px 0 7px; font-size:13px; }}
.map {{ height:690px; width:100%; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; }}
.chip {{ display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); background:#fff; border-radius:7px; padding:6px 8px; font-size:13px; cursor:pointer; }}
.chip input {{ margin:0; }}
.btnrow {{ display:flex; gap:8px; margin-top:8px; }}
button {{ border:1px solid var(--line); background:#fff; border-radius:7px; padding:7px 9px; cursor:pointer; font:inherit; }}
button:hover {{ border-color:#9aa8b8; }}
.metric-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
.metric {{ border:1px solid var(--line); border-radius:8px; padding:9px; background:#fbfcfe; }}
.metric b {{ display:block; font-size:20px; }}
.metric span {{ color:var(--muted); font-size:12px; }}
.note {{ color:var(--muted); font-size:12px; line-height:1.35; }}
.table-wrap {{ max-height:310px; overflow:auto; border:1px solid var(--line); border-radius:7px; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th,td {{ padding:6px 7px; border-bottom:1px solid #edf1f6; text-align:left; white-space:nowrap; }}
th {{ position:sticky; top:0; background:#f8fafc; z-index:1; }}
.chart {{ height:250px; }}
.legend {{ background:#fff; padding:8px 9px; border:1px solid var(--line); border-radius:7px; font-size:12px; line-height:1.35; box-shadow:0 2px 12px rgba(16,24,40,.08); }}
.swatch {{ display:inline-block; width:10px; height:10px; margin-right:5px; vertical-align:-1px; }}
.search {{ width:100%; border:1px solid var(--line); border-radius:7px; padding:8px; margin:8px 0; }}
@media (max-width: 980px) {{ .layout {{ grid-template-columns:1fr; }} .map {{ height:560px; }} }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Hurricane Mitch Extended Best Track</h1>
    <p class="sub">Interactive view of EBTRK storm-center records, four-quadrant wind radii, and municipality polygons selected by threshold/quadrant overlap. Red municipalities are selected only from the current wind-radii controls.</p>
  </div>
</header>
<main>
  <div class="layout">
    <aside class="panel pad">
      <h2>Wind-Radii Selection</h2>
      <h3>Thresholds</h3>
      <div class="chips" id="thresholdControls"></div>
      <h3>Quadrants</h3>
      <div class="chips" id="quadrantControls"></div>
      <div class="btnrow">
        <button id="allQuadrants">All quadrants</button>
        <button id="clearQuadrants">Clear quadrants</button>
      </div>
      <p class="note">Selection rule: a municipality turns red if any part of its polygon overlaps any selected threshold-quadrant swath over Mitch's EBTRK life. A municipality can belong to multiple quadrants because the storm center moves.</p>
      <div class="metric-grid" id="metrics"></div>
      <h3>Selected Municipalities</h3>
      <input class="search" id="muniSearch" placeholder="Filter municipality table">
      <div class="table-wrap"><table id="muniTable"></table></div>
      <h3>Selected Summary</h3>
      <div class="table-wrap"><table id="summaryTable"></table></div>
    </aside>
    <section class="panel">
      <div id="map" class="map"></div>
    </section>
  </div>
  <div class="layout" style="margin-top:14px;">
    <section class="panel pad">
      <h2>Track Intensity And Pressure</h2>
      <div id="trackChart" class="chart"></div>
    </section>
    <section class="panel pad">
      <h2>EBTRK Records</h2>
      <p class="note">Rows are 6-hourly Extended Best Track observations. Radii are nautical miles by quadrant.</p>
      <div class="table-wrap"><table id="recordTable"></table></div>
    </section>
  </div>
</main>
<script>
const PAYLOAD = {safe_json(payload)};
const MUNICIPALITIES = PAYLOAD.municipalities;
const SWATHS = PAYLOAD.swaths;
const TRACK_POINTS = PAYLOAD.trackPoints;
const TRACK_LINE = PAYLOAD.trackLine;
const RECORDS = PAYLOAD.records;
const SUMMARY = PAYLOAD.summary;
const THRESHOLDS = [
  {{ key:'r34', label:'34 kt', color:'#0f766e' }},
  {{ key:'r50', label:'50 kt', color:'#d97706' }},
  {{ key:'r64', label:'64 kt', color:'#b91c1c' }}
];
const QUADRANTS = ['NE','SE','SW','NW'];
const state = {{ thresholds:new Set(['r64']), quadrants:new Set(['NE','SE','SW','NW']), search:'' }};
function fmt(x, d=0) {{ return x === null || x === undefined || Number.isNaN(Number(x)) ? '' : Number(x).toLocaleString(undefined, {{ maximumFractionDigits:d, minimumFractionDigits:d }}); }}
function shareKey(t, q) {{ return `share_${{t}}_${{q.toLowerCase()}}`; }}
function selectedShare(props) {{
  let best = 0;
  state.thresholds.forEach(t => state.quadrants.forEach(q => {{ best = Math.max(best, Number(props[shareKey(t,q)]) || 0); }}));
  return best;
}}
function selectedCombos() {{
  const out = [];
  state.thresholds.forEach(t => state.quadrants.forEach(q => out.push([t,q])));
  return out;
}}
function thresholdColor(t) {{ return THRESHOLDS.find(x => x.key === t)?.color || '#64748b'; }}
function swathStyle(feature) {{
  const p = feature.properties;
  const active = state.thresholds.has(p.threshold) && state.quadrants.has(p.quadrant);
  return {{ color:thresholdColor(p.threshold), weight:active ? 2 : 0.8, opacity:active ? 0.9 : 0.08, fillColor:thresholdColor(p.threshold), fillOpacity:active ? 0.17 : 0.015, dashArray:p.quadrant === 'NE' ? null : p.quadrant === 'SE' ? '5 5' : p.quadrant === 'SW' ? '2 5' : '8 4' }};
}}
function muniStyle(feature) {{
  const s = selectedShare(feature.properties);
  return {{ color:s > 0 ? '#7f1d1d' : '#cbd5e1', weight:s > 0 ? 1.2 : 0.45, fillColor:s > 0 ? '#b91c1c' : '#eef2f7', fillOpacity:s > 0 ? 0.72 : 0.34 }};
}}
function popupMuni(props) {{
  const combos = selectedCombos().map(([t,q]) => `${{t.toUpperCase()}} ${{q}}: ${{fmt((Number(props[shareKey(t,q)]) || 0) * 100, 1)}}%`).join('<br>');
  return `<b>${{props.municipality_name || ''}}</b><br>${{props.country_display || props.country_name || ''}}<br><br>${{combos}}`;
}}
function popupTrack(props) {{
  const rows = THRESHOLDS.map(t => `${{t.toUpperCase()}} NE/SE/SW/NW: ${{fmt(props[`${{t}}_ne_nm`])}} / ${{fmt(props[`${{t}}_se_nm`])}} / ${{fmt(props[`${{t}}_sw_nm`])}} / ${{fmt(props[`${{t}}_nw_nm`])}} nm`).join('<br>');
  return `<b>${{props.iso_time}}</b><br>Wind: ${{fmt(props.vmax_kt)}} kt<br>Pressure: ${{fmt(props.pressure_mb)}} mb<br>${{rows}}`;
}}
function initControls() {{
  document.getElementById('thresholdControls').innerHTML = THRESHOLDS.map(t => `<label class="chip" style="border-color:${{t.color}}55"><input type="checkbox" data-threshold="${{t.key}}" ${{state.thresholds.has(t.key) ? 'checked' : ''}}> ${{t.label}}</label>`).join('');
  document.getElementById('quadrantControls').innerHTML = QUADRANTS.map(q => `<label class="chip"><input type="checkbox" data-quadrant="${{q}}" ${{state.quadrants.has(q) ? 'checked' : ''}}> ${{q}}</label>`).join('');
  document.querySelectorAll('[data-threshold]').forEach(el => el.addEventListener('change', e => {{ e.target.checked ? state.thresholds.add(e.target.dataset.threshold) : state.thresholds.delete(e.target.dataset.threshold); updateAll(); }}));
  document.querySelectorAll('[data-quadrant]').forEach(el => el.addEventListener('change', e => {{ e.target.checked ? state.quadrants.add(e.target.dataset.quadrant) : state.quadrants.delete(e.target.dataset.quadrant); updateAll(); }}));
  document.getElementById('allQuadrants').addEventListener('click', () => {{ state.quadrants = new Set(QUADRANTS); initControls(); updateAll(); }});
  document.getElementById('clearQuadrants').addEventListener('click', () => {{ state.quadrants = new Set(); initControls(); updateAll(); }});
  document.getElementById('muniSearch').addEventListener('input', e => {{ state.search = e.target.value.toLowerCase(); renderMuniTable(); }});
}}
const map = L.map('map', {{ preferCanvas:true }}).setView([15.6, -85.5], 6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom:10, attribution:'&copy; OpenStreetMap contributors' }}).addTo(map);
const swathLayer = L.geoJSON(SWATHS, {{ style:swathStyle, onEachFeature:(f,l) => l.bindPopup(`<b>${{f.properties.threshold.toUpperCase()}} ${{f.properties.quadrant}}</b><br>Records: ${{f.properties.records_with_radius}}<br>Max radius: ${{fmt(f.properties.max_radius_nm)}} nm`) }}).addTo(map);
const muniLayer = L.geoJSON(MUNICIPALITIES, {{ style:muniStyle, onEachFeature:(f,l) => l.bindPopup(() => popupMuni(f.properties)) }}).addTo(map);
const trackLine = L.geoJSON(TRACK_LINE, {{ style:{{ color:'#111827', weight:3, opacity:.9 }} }}).addTo(map);
const trackPoints = L.geoJSON(TRACK_POINTS, {{ pointToLayer:(f,latlng) => L.circleMarker(latlng, {{ radius:3.5, color:'#111827', fillColor:'#fff', fillOpacity:1, weight:1.1 }}), onEachFeature:(f,l) => l.bindPopup(() => popupTrack(f.properties)) }}).addTo(map);
L.control.layers({{}}, {{ 'Selected wind swaths':swathLayer, 'Municipalities':muniLayer, 'EBTRK track':trackLine, 'EBTRK points':trackPoints }}, {{ collapsed:false }}).addTo(map);
const legend = L.control({{ position:'bottomright' }});
legend.onAdd = function() {{ const div = L.DomUtil.create('div','legend'); div.innerHTML = '<b>Wind radii</b><br><span class="swatch" style="background:#0f766e"></span>34 kt<br><span class="swatch" style="background:#d97706"></span>50 kt<br><span class="swatch" style="background:#b91c1c"></span>64 kt<br><span class="swatch" style="background:#b91c1c"></span>red municipality = selected'; return div; }};
legend.addTo(map);
map.fitBounds(muniLayer.getBounds(), {{ padding:[16,16] }});
function selectedRows() {{
  return MUNICIPALITIES.features.map(f => ({{ ...f.properties, selected_share:selectedShare(f.properties) }})).filter(r => r.selected_share > 0);
}}
function updateMetrics() {{
  const rows = selectedRows();
  const countryCounts = new Map();
  rows.forEach(r => {{
    const country = r.country_display || r.country_name || '';
    countryCounts.set(country, (countryCounts.get(country) || 0) + 1);
  }});
  const countries = [...countryCounts.entries()].sort((a,b) => b[1]-a[1]).map(([k,v]) => `${{k}}: ${{v}}`).join('<br>');
  const maxWind = Math.max(...RECORDS.map(r => Number(r.vmax_kt) || 0));
  document.getElementById('metrics').innerHTML = `
    <div class="metric"><b>${{rows.length}}</b><span>selected municipalities</span></div>
    <div class="metric"><b>${{state.thresholds.size * state.quadrants.size}}</b><span>active threshold-quadrants</span></div>
    <div class="metric"><b>${{maxWind}}</b><span>max EBTRK wind kt</span></div>
    <div class="metric"><b>${{RECORDS.length}}</b><span>6-hourly EBTRK rows</span></div>
    <div class="metric" style="grid-column:1 / -1;"><span>Selected by country</span><br>${{countries || 'None'}}</div>`;
}}
function renderMuniTable() {{
  const rows = selectedRows().filter(r => !state.search || `${{r.country_display || r.country_name}} ${{r.department_name}} ${{r.municipality_name}}`.toLowerCase().includes(state.search)).sort((a,b) => (b.selected_share - a.selected_share) || String(a.country_display || a.country_name).localeCompare(String(b.country_display || b.country_name)) || String(a.municipality_name).localeCompare(String(b.municipality_name)));
  const body = rows.map(r => `<tr><td>${{r.country_display || r.country_name || ''}}</td><td>${{r.municipality_name || ''}}</td><td>${{fmt(r.selected_share * 100,1)}}%</td></tr>`).join('');
  document.getElementById('muniTable').innerHTML = `<thead><tr><th>Country</th><th>Municipality</th><th>Max selected share</th></tr></thead><tbody>${{body || '<tr><td colspan="3">No municipalities selected.</td></tr>'}}</tbody>`;
}}
function renderSummaryTable() {{
  const active = SUMMARY.filter(r => state.thresholds.has(r.threshold) && (!r.quadrant || state.quadrants.has(r.quadrant)));
  const body = active.map(r => `<tr><td>${{r.threshold.toUpperCase()}}</td><td>${{r.quadrant || 'All selected quadrants'}}</td><td>${{r.municipalities_any}}</td><td>${{r.municipalities_50pct}}</td></tr>`).join('');
  document.getElementById('summaryTable').innerHTML = `<thead><tr><th>Threshold</th><th>Quadrant</th><th>Any</th><th>Max share >=50%</th></tr></thead><tbody>${{body}}</tbody>`;
}}
function renderRecordTable() {{
  const rows = RECORDS.map(r => `<tr><td>${{r.iso_time}}</td><td>${{fmt(r.lat,1)}}, ${{fmt(r.lon,1)}}</td><td>${{fmt(r.vmax_kt)}}</td><td>${{fmt(r.pressure_mb)}}</td><td>${{fmt(r.r34_ne_nm)}}/${{fmt(r.r34_se_nm)}}/${{fmt(r.r34_sw_nm)}}/${{fmt(r.r34_nw_nm)}}</td><td>${{fmt(r.r50_ne_nm)}}/${{fmt(r.r50_se_nm)}}/${{fmt(r.r50_sw_nm)}}/${{fmt(r.r50_nw_nm)}}</td><td>${{fmt(r.r64_ne_nm)}}/${{fmt(r.r64_se_nm)}}/${{fmt(r.r64_sw_nm)}}/${{fmt(r.r64_nw_nm)}}</td></tr>`).join('');
  document.getElementById('recordTable').innerHTML = `<thead><tr><th>Time</th><th>Center</th><th>Wind kt</th><th>Pressure</th><th>R34 NE/SE/SW/NW</th><th>R50 NE/SE/SW/NW</th><th>R64 NE/SE/SW/NW</th></tr></thead><tbody>${{rows}}</tbody>`;
}}
function renderChart() {{
  const x = RECORDS.map(r => r.iso_time);
  Plotly.newPlot('trackChart', [
    {{ x, y:RECORDS.map(r => r.vmax_kt), type:'scatter', mode:'lines+markers', name:'Wind kt', line:{{ color:'#b91c1c', width:2 }} }},
    {{ x, y:RECORDS.map(r => r.pressure_mb), type:'scatter', mode:'lines+markers', name:'Pressure mb', yaxis:'y2', line:{{ color:'#2563eb', width:2 }} }}
  ], {{ margin:{{ l:45, r:48, t:10, b:45 }}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', xaxis:{{ tickangle:-30 }}, yaxis:{{ title:'Wind kt' }}, yaxis2:{{ title:'Pressure mb', overlaying:'y', side:'right', autorange:'reversed' }}, legend:{{ orientation:'h', y:1.15 }} }}, {{ displayModeBar:false, responsive:true }});
}}
function updateAll() {{
  swathLayer.setStyle(swathStyle);
  muniLayer.setStyle(muniStyle);
  updateMetrics();
  renderMuniTable();
  renderSummaryTable();
}}
initControls();
renderRecordTable();
renderChart();
updateAll();
</script>
</body>
</html>
"""


def main() -> int:
    ebtrk = load_ebtrk()
    municipalities = load_municipalities()
    swaths, swath_geoms = build_swath_layers(ebtrk)
    municipalities = add_exposure_properties(municipalities, swath_geoms)
    track_points, track_line = track_geojson(ebtrk)
    payload = {
        "municipalities": municipality_geojson(municipalities),
        "swaths": swaths,
        "trackPoints": track_points,
        "trackLine": track_line,
        "records": records_for_js(ebtrk),
        "summary": summary_records(municipalities),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render_html(payload), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
