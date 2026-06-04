from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = ROOT / "working" / "data" / "web" / "did_besttrack_chirps_municipalities.geojson"
OUT_PATH = ROOT / "out" / "chirps_dashboard.html"


def compact_geojson(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CHIRPS Rainfall Dashboard</title>
<style>
:root {
  color-scheme: light;
  --bg: #f6f7f8;
  --ink: #202326;
  --muted: #66717d;
  --line: #d8dde3;
  --panel: #ffffff;
  --accent: #b91c1c;
  --accent-dark: #7f1d1d;
  --accent-soft: #fee2e2;
  --blue: #1d4ed8;
  --green: #047857;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
button, select, input { font: inherit; }
.app {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  min-height: 100vh;
}
header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--line);
  background: #ffffff;
}
h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.15;
  font-weight: 760;
  letter-spacing: 0;
}
.subtitle {
  margin-top: 4px;
  color: var(--muted);
  font-size: 13px;
}
.source {
  color: var(--muted);
  font-size: 12px;
  text-align: right;
  max-width: 470px;
}
.toolbar {
  display: grid;
  grid-template-columns: repeat(6, minmax(150px, 1fr));
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  background: #eef1f4;
}
.control {
  min-width: 0;
}
.control label {
  display: block;
  margin: 0 0 4px;
  color: #424b55;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.control select, .control input {
  width: 100%;
  min-height: 34px;
  border: 1px solid #c7ced6;
  border-radius: 6px;
  background: #ffffff;
  color: var(--ink);
  padding: 6px 8px;
}
.toggle-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 6px 8px;
  border: 1px solid #c7ced6;
  border-radius: 6px;
  background: #ffffff;
}
.toggle-row input { width: auto; min-height: auto; }
.main {
  display: grid;
  grid-template-columns: minmax(460px, 1fr) 420px;
  gap: 0;
  min-height: 0;
}
.map-pane {
  position: relative;
  min-height: 620px;
  background: #fbfcfd;
  overflow: hidden;
}
#mapCanvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}
.legend {
  position: absolute;
  left: 16px;
  bottom: 16px;
  width: min(360px, calc(100% - 32px));
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.12);
}
.legend-title {
  font-size: 12px;
  font-weight: 750;
  margin-bottom: 8px;
}
.gradient {
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, #fff5f5, #fecaca, #ef4444, #991b1b);
  border: 1px solid #f3b4b4;
}
.legend-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
}
.tooltip {
  position: absolute;
  pointer-events: none;
  z-index: 10;
  display: none;
  max-width: 280px;
  padding: 9px 10px;
  border-radius: 7px;
  border: 1px solid var(--line);
  background: rgba(255,255,255,0.97);
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.16);
  font-size: 12px;
}
.tooltip strong { display: block; font-size: 13px; margin-bottom: 3px; }
.side {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  border-left: 1px solid var(--line);
  background: var(--panel);
  min-width: 0;
}
.stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--line);
}
.stat {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 9px;
  background: #fbfcfd;
}
.stat .label { color: var(--muted); font-size: 11px; }
.stat .value { margin-top: 2px; font-size: 18px; font-weight: 760; }
.hist-wrap {
  padding: 10px 12px 12px;
  border-bottom: 1px solid var(--line);
}
.hist-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted);
}
#histogram {
  display: block;
  width: 100%;
  height: 118px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
}
.table-wrap {
  overflow: auto;
  min-height: 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th, td {
  padding: 8px 9px;
  border-bottom: 1px solid #edf0f3;
  text-align: left;
  vertical-align: top;
}
th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  color: #44505c;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.rank { color: var(--muted); width: 42px; }
.pill {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-dark);
  font-size: 11px;
  font-weight: 700;
}
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}
button {
  min-height: 34px;
  border: 1px solid #b8c1cc;
  border-radius: 6px;
  background: #ffffff;
  color: #26313d;
  padding: 6px 10px;
  cursor: pointer;
}
button:hover { border-color: #8b96a3; background: #f8fafc; }
@media (max-width: 1120px) {
  .toolbar { grid-template-columns: repeat(3, minmax(160px, 1fr)); }
  .main { grid-template-columns: 1fr; }
  .side { border-left: 0; border-top: 1px solid var(--line); }
  .map-pane { min-height: 520px; }
  header { align-items: start; flex-direction: column; }
  .source { text-align: left; }
}
@media (max-width: 720px) {
  .toolbar { grid-template-columns: 1fr; }
  .stats { grid-template-columns: 1fr 1fr; }
  .map-pane { min-height: 430px; }
}
</style>
</head>
<body>
<div class="app">
  <header>
    <div>
      <h1>CHIRPS Rainfall Dashboard</h1>
      <div class="subtitle">Municipality rainfall levels and anomalies during Hurricane Mitch, sortable by wind-swath exposure.</div>
    </div>
    <div class="source">Data lineage: processed CHIRPS municipality zonal statistics and EBTRK wind-swath shares from <code>working/data/web/did_besttrack_chirps_municipalities.geojson</code>.</div>
  </header>

  <section class="toolbar" aria-label="Dashboard controls">
    <div class="control">
      <label for="metric">Rainfall metric</label>
      <select id="metric">
        <option value="rain_total_mean_mm">Average rainfall</option>
        <option value="rain_total_max_pixel_mm">Maximum rainfall</option>
        <option value="rain_total_anomaly_mm">Average rainfall anomaly</option>
        <option value="rain_max_daily_anomaly_mm">Maximum rainfall anomaly</option>
      </select>
    </div>
    <div class="control">
      <label for="swath">Wind swath filter</label>
      <select id="swath">
        <option value="all">All municipalities</option>
        <option value="r64_any">Within 64 kt swath</option>
        <option value="r50_any">Within 50 kt swath</option>
        <option value="r34_any">Within 34 kt swath</option>
        <option value="r64_half">At least 50% in 64 kt</option>
        <option value="r50_half">At least 50% in 50 kt</option>
        <option value="r34_half">At least 50% in 34 kt</option>
        <option value="outside">Outside wind swaths</option>
      </select>
    </div>
    <div class="control">
      <label for="country">Country</label>
      <select id="country"></select>
    </div>
    <div class="control">
      <label for="topMode">Highlight</label>
      <select id="topMode">
        <option value="all">Full distribution</option>
        <option value="top10">Top 10%</option>
        <option value="top25">Top 25%</option>
        <option value="top50">Top 50 municipalities</option>
      </select>
    </div>
    <div class="control">
      <label for="positiveOnly">Anomaly rule</label>
      <div class="toggle-row"><input id="positiveOnly" type="checkbox"><span>Positive anomalies only</span></div>
    </div>
    <div class="actions">
      <button id="resetBtn" type="button">Reset</button>
      <button id="csvBtn" type="button">Export CSV</button>
    </div>
  </section>

  <main class="main">
    <section class="map-pane">
      <canvas id="mapCanvas"></canvas>
      <div id="tooltip" class="tooltip"></div>
      <div class="legend">
        <div id="legendTitle" class="legend-title">Average rainfall</div>
        <div class="gradient"></div>
        <div class="legend-scale"><span id="legendMin">0</span><span id="legendMax">0</span></div>
      </div>
    </section>
    <aside class="side">
      <section class="stats">
        <div class="stat"><div class="label">Municipalities shown</div><div id="statCount" class="value">0</div></div>
        <div class="stat"><div class="label">Mean selected metric</div><div id="statMean" class="value">--</div></div>
        <div class="stat"><div class="label">Top municipality</div><div id="statTop" class="value">--</div></div>
        <div class="stat"><div class="label">Median swath share</div><div id="statSwath" class="value">--</div></div>
      </section>
      <section class="hist-wrap">
        <div class="hist-head"><strong>Distribution</strong><span id="histLabel">Selected metric</span></div>
        <canvas id="histogram"></canvas>
      </section>
      <section class="table-wrap">
        <table>
          <thead><tr><th class="rank">#</th><th>Municipality</th><th class="num">Metric</th><th class="num">64/50/34 share</th></tr></thead>
          <tbody id="rankRows"></tbody>
        </table>
      </section>
    </aside>
  </main>
</div>
<script>
const GEOJSON = __GEOJSON__;
const METRICS = {
  rain_total_mean_mm: { label: 'Average rainfall', short: 'Avg rain', unit: 'mm', help: 'Mean municipality cumulative rainfall over the Mitch CHIRPS window.' },
  rain_total_max_pixel_mm: { label: 'Maximum rainfall', short: 'Max rain', unit: 'mm', help: 'Maximum cumulative CHIRPS pixel inside the municipality.' },
  rain_total_anomaly_mm: { label: 'Average rainfall anomaly', short: 'Avg anomaly', unit: 'mm', help: 'Mean cumulative Mitch rainfall minus historical cumulative mean.' },
  rain_max_daily_anomaly_mm: { label: 'Maximum rainfall anomaly', short: 'Max anomaly', unit: 'mm', help: 'Mean maximum-daily Mitch rainfall minus historical maximum-daily mean.' }
};
const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');
const histCanvas = document.getElementById('histogram');
const histCtx = histCanvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
const controls = {
  metric: document.getElementById('metric'),
  swath: document.getElementById('swath'),
  country: document.getElementById('country'),
  topMode: document.getElementById('topMode'),
  positiveOnly: document.getElementById('positiveOnly')
};
const features = GEOJSON.features.map((feature, index) => ({
  index,
  feature,
  props: feature.properties,
  path: null,
  included: true,
  highlighted: true,
  value: NaN
}));
let bounds = computeBounds(features);
let transform = null;
let activeRows = [];
let hoverItem = null;
let selectedItem = null;

function finiteNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : NaN;
}
function fmt(value, digits = 1) {
  const n = finiteNumber(value);
  if (!Number.isFinite(n)) return '--';
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
function fmtLoose(value, digits = 1) {
  const n = finiteNumber(value);
  if (!Number.isFinite(n)) return '--';
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}
function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function computeBounds(items) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  function visit(coord) {
    const x = coord[0], y = coord[1];
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  for (const item of items) walkCoords(item.feature.geometry, visit);
  return { minX, minY, maxX, maxY };
}
function walkCoords(geometry, fn) {
  if (!geometry) return;
  const coords = geometry.coordinates;
  if (geometry.type === 'Polygon') {
    for (const ring of coords) for (const coord of ring) fn(coord);
  } else if (geometry.type === 'MultiPolygon') {
    for (const poly of coords) for (const ring of poly) for (const coord of ring) fn(coord);
  }
}
function polygonRings(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
}
function setCanvasSize() {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const histRect = histCanvas.getBoundingClientRect();
  histCanvas.width = Math.max(1, Math.floor(histRect.width * dpr));
  histCanvas.height = Math.max(1, Math.floor(histRect.height * dpr));
  histCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function projection() {
  const rect = canvas.getBoundingClientRect();
  const pad = 24;
  const width = Math.max(1, rect.width - pad * 2);
  const height = Math.max(1, rect.height - pad * 2);
  const xSpan = bounds.maxX - bounds.minX;
  const ySpan = bounds.maxY - bounds.minY;
  const scale = Math.min(width / xSpan, height / ySpan);
  const xOffset = (rect.width - xSpan * scale) / 2;
  const yOffset = (rect.height - ySpan * scale) / 2;
  return {
    project(coord) {
      return [xOffset + (coord[0] - bounds.minX) * scale, yOffset + (bounds.maxY - coord[1]) * scale];
    }
  };
}
function buildPath(geometry) {
  const p = new Path2D();
  for (const ring of polygonRings(geometry)) {
    ring.forEach((coord, i) => {
      const [x, y] = transform.project(coord);
      if (i === 0) p.moveTo(x, y); else p.lineTo(x, y);
    });
    p.closePath();
  }
  return p;
}
function swathShare(props, threshold) {
  return finiteNumber(props[`share_area_${threshold}`]);
}
function passesSwath(props) {
  const value = controls.swath.value;
  if (value === 'all') return true;
  if (value === 'outside') return !(swathShare(props, 'r64') > 0 || swathShare(props, 'r50') > 0 || swathShare(props, 'r34') > 0);
  const [threshold, mode] = value.split('_');
  const share = swathShare(props, threshold);
  return mode === 'half' ? share >= 0.5 : share > 0;
}
function selectedSwathShare(props) {
  const value = controls.swath.value;
  if (value.startsWith('r64')) return swathShare(props, 'r64');
  if (value.startsWith('r50')) return swathShare(props, 'r50');
  if (value.startsWith('r34')) return swathShare(props, 'r34');
  return Math.max(swathShare(props, 'r64') || 0, swathShare(props, 'r50') || 0, swathShare(props, 'r34') || 0);
}
function isAnomalyMetric() {
  return controls.metric.value.includes('anomaly');
}
function passesFilters(item) {
  const props = item.props;
  if (controls.country.value !== 'all' && props.country_name !== controls.country.value) return false;
  if (!passesSwath(props)) return false;
  const value = finiteNumber(props[controls.metric.value]);
  if (!Number.isFinite(value)) return false;
  if (controls.positiveOnly.checked && isAnomalyMetric() && value <= 0) return false;
  return true;
}
function quantile(values, q) {
  if (!values.length) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}
function colorFor(value, min, max, included, highlighted) {
  if (!included) return '#e3e7eb';
  if (!highlighted) return '#f6d7d7';
  if (!(max > min)) return '#ef4444';
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const stops = [
    [1.00, 0.96, 0.96],
    [0.99, 0.80, 0.80],
    [0.94, 0.27, 0.27],
    [0.60, 0.11, 0.11]
  ];
  const scaled = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(scaled));
  const local = scaled - i;
  const a = stops[i], b = stops[i + 1];
  const rgb = a.map((v, idx) => Math.round((v + (b[idx] - v) * local) * 255));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}
function update() {
  const metric = controls.metric.value;
  activeRows = [];
  for (const item of features) {
    item.value = finiteNumber(item.props[metric]);
    item.included = passesFilters(item);
    item.highlighted = false;
    if (item.included) activeRows.push(item);
  }
  activeRows.sort((a, b) => b.value - a.value);
  const mode = controls.topMode.value;
  let limit = activeRows.length;
  if (mode === 'top10') limit = Math.ceil(activeRows.length * 0.10);
  if (mode === 'top25') limit = Math.ceil(activeRows.length * 0.25);
  if (mode === 'top50') limit = Math.min(50, activeRows.length);
  activeRows.forEach((item, idx) => { item.highlighted = idx < limit; });
  drawMap();
  drawHistogram();
  renderStats();
  renderTable();
}
function drawMap() {
  setCanvasSize();
  transform = projection();
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = '#fbfcfd';
  ctx.fillRect(0, 0, rect.width, rect.height);
  const values = activeRows.map(r => r.value).filter(Number.isFinite);
  const min = quantile(values, 0.02);
  const max = quantile(values, 0.98);
  for (const item of features) {
    item.path = buildPath(item.feature.geometry);
    ctx.fillStyle = colorFor(item.value, min, max, item.included, item.highlighted);
    ctx.strokeStyle = item.included ? 'rgba(95, 42, 42, 0.55)' : 'rgba(120, 130, 140, 0.22)';
    ctx.lineWidth = item.included ? 0.55 : 0.35;
    ctx.fill(item.path);
    ctx.stroke(item.path);
  }
  const target = selectedItem || hoverItem;
  if (target && target.path) {
    ctx.save();
    ctx.strokeStyle = '#1d4ed8';
    ctx.lineWidth = 2.4;
    ctx.stroke(target.path);
    ctx.restore();
  }
  document.getElementById('legendTitle').textContent = METRICS[controls.metric.value].label;
  document.getElementById('legendMin').textContent = fmtLoose(min, 1) + ' mm';
  document.getElementById('legendMax').textContent = fmtLoose(max, 1) + ' mm';
}
function drawHistogram() {
  const rect = histCanvas.getBoundingClientRect();
  histCtx.clearRect(0, 0, rect.width, rect.height);
  histCtx.fillStyle = '#ffffff';
  histCtx.fillRect(0, 0, rect.width, rect.height);
  const values = activeRows.map(r => r.value).filter(Number.isFinite);
  document.getElementById('histLabel').textContent = METRICS[controls.metric.value].short;
  if (!values.length) return;
  const min = Math.min(...values), max = Math.max(...values);
  const bins = 18;
  const counts = new Array(bins).fill(0);
  for (const v of values) {
    const idx = max === min ? 0 : Math.min(bins - 1, Math.floor(((v - min) / (max - min)) * bins));
    counts[idx] += 1;
  }
  const maxCount = Math.max(...counts);
  const pad = 12;
  const barGap = 2;
  const w = (rect.width - pad * 2 - barGap * (bins - 1)) / bins;
  counts.forEach((count, i) => {
    const h = maxCount ? (rect.height - pad * 2) * count / maxCount : 0;
    const x = pad + i * (w + barGap);
    const y = rect.height - pad - h;
    const t = bins <= 1 ? 1 : i / (bins - 1);
    histCtx.fillStyle = colorFor(min + (max - min) * t, min, max, true, true);
    histCtx.fillRect(x, y, w, h);
  });
}
function renderStats() {
  const values = activeRows.map(r => r.value).filter(Number.isFinite);
  const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : NaN;
  const top = activeRows[0];
  const shares = activeRows.map(r => selectedSwathShare(r.props)).filter(Number.isFinite);
  document.getElementById('statCount').textContent = activeRows.length.toLocaleString();
  document.getElementById('statMean').textContent = fmtLoose(mean, 1) + ' mm';
  document.getElementById('statTop').textContent = top ? top.props.municipality_name : '--';
  document.getElementById('statSwath').textContent = shares.length ? fmtLoose(quantile(shares, 0.5) * 100, 1) + '%' : '--';
}
function renderTable() {
  const rows = activeRows.slice(0, 120).map((item, idx) => {
    const p = item.props;
    const shares = [swathShare(p, 'r64'), swathShare(p, 'r50'), swathShare(p, 'r34')].map(v => fmtLoose((v || 0) * 100, 0) + '%').join('/');
    return `<tr data-index="${item.index}"><td class="rank">${idx + 1}</td><td><strong>${escapeHtml(p.municipality_name)}</strong><br><span class="pill">${escapeHtml(p.country_name)}</span> <span>${escapeHtml(p.department_name)}</span></td><td class="num">${fmtLoose(item.value, 1)}</td><td class="num">${shares}</td></tr>`;
  }).join('');
  document.getElementById('rankRows').innerHTML = rows || '<tr><td colspan="4">No municipalities match the current filters.</td></tr>';
}
function itemAt(x, y) {
  for (let i = features.length - 1; i >= 0; i--) {
    const item = features[i];
    if (item.path && ctx.isPointInPath(item.path, x, y)) return item;
  }
  return null;
}
function tooltipHtml(item) {
  const p = item.props;
  return `<strong>${escapeHtml(p.municipality_name)}</strong>
    ${escapeHtml(p.department_name)}, ${escapeHtml(p.country_name)}<br>
    ${escapeHtml(METRICS[controls.metric.value].label)}: <b>${fmtLoose(item.value, 1)} mm</b><br>
    Average rain: ${fmtLoose(p.rain_total_mean_mm, 1)} mm<br>
    Max rain: ${fmtLoose(p.rain_total_max_pixel_mm, 1)} mm<br>
    Avg anomaly: ${fmtLoose(p.rain_total_anomaly_mm, 1)} mm<br>
    Max anomaly: ${fmtLoose(p.rain_max_daily_anomaly_mm, 1)} mm<br>
    Swath share 64/50/34 kt: ${fmtLoose(swathShare(p, 'r64') * 100, 1)}% / ${fmtLoose(swathShare(p, 'r50') * 100, 1)}% / ${fmtLoose(swathShare(p, 'r34') * 100, 1)}%`;
}
canvas.addEventListener('mousemove', event => {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const item = itemAt(x, y);
  if (item !== hoverItem) {
    hoverItem = item;
    drawMap();
  }
  if (item) {
    tooltip.style.display = 'block';
    tooltip.innerHTML = tooltipHtml(item);
    tooltip.style.left = Math.min(rect.width - 300, x + 14) + 'px';
    tooltip.style.top = Math.max(8, y + 14) + 'px';
  } else {
    tooltip.style.display = 'none';
  }
});
canvas.addEventListener('mouseleave', () => {
  hoverItem = null;
  tooltip.style.display = 'none';
  drawMap();
});
canvas.addEventListener('click', event => {
  const rect = canvas.getBoundingClientRect();
  selectedItem = itemAt(event.clientX - rect.left, event.clientY - rect.top);
  drawMap();
});
document.getElementById('rankRows').addEventListener('mouseover', event => {
  const tr = event.target.closest('tr[data-index]');
  if (!tr) return;
  hoverItem = features[Number(tr.dataset.index)];
  drawMap();
});
document.getElementById('rankRows').addEventListener('mouseleave', () => {
  hoverItem = null;
  drawMap();
});
document.getElementById('rankRows').addEventListener('click', event => {
  const tr = event.target.closest('tr[data-index]');
  if (!tr) return;
  selectedItem = features[Number(tr.dataset.index)];
  drawMap();
});
function populateCountries() {
  const countries = Array.from(new Set(features.map(f => f.props.country_name).filter(Boolean))).sort();
  controls.country.innerHTML = '<option value="all">All countries</option>' + countries.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
}
function exportCsv() {
  const metric = controls.metric.value;
  const header = ['rank','municipality','department','country','metric','metric_value_mm','rain_total_mean_mm','rain_total_max_pixel_mm','rain_total_anomaly_mm','rain_max_daily_anomaly_mm','share_area_r64','share_area_r50','share_area_r34'];
  const lines = [header.join(',')];
  activeRows.forEach((item, idx) => {
    const p = item.props;
    const row = [idx + 1, p.municipality_name, p.department_name, p.country_name, METRICS[metric].label, item.value, p.rain_total_mean_mm, p.rain_total_max_pixel_mm, p.rain_total_anomaly_mm, p.rain_max_daily_anomaly_mm, p.share_area_r64, p.share_area_r50, p.share_area_r34]
      .map(v => `"${String(v ?? '').replace(/"/g, '""')}"`);
    lines.push(row.join(','));
  });
  const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `chirps_dashboard_${metric}_${controls.swath.value}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
for (const el of Object.values(controls)) el.addEventListener('change', update);
document.getElementById('resetBtn').addEventListener('click', () => {
  controls.metric.value = 'rain_total_mean_mm';
  controls.swath.value = 'all';
  controls.country.value = 'all';
  controls.topMode.value = 'all';
  controls.positiveOnly.checked = false;
  selectedItem = null;
  update();
});
document.getElementById('csvBtn').addEventListener('click', exportCsv);
window.addEventListener('resize', () => drawMap());
populateCountries();
update();
</script>
</body>
</html>
'''


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing dashboard source data: {DATA_PATH}")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html = HTML_TEMPLATE.replace("__GEOJSON__", compact_geojson(DATA_PATH))
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
