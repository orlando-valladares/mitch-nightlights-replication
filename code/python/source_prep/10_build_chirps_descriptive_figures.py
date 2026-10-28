from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from matplotlib import pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pyproj import Geod
from rasterio.features import rasterize


matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "raw"
WORKING = ROOT / "working"
OUT = ROOT / "out"
OVERLEAF_OUT = ROOT / "paper" / "Paper_Figures" / "data" / "CHIRPS"
FIGURE_OUT = OUT / "figures" / "chirps"
DATA_OUT = WORKING / "data" / "processed"

MITCH_PATH = RAW / "chirps_mitch_daily_stack_19981027_19981104_ca5.tif"
CLIM_PATH = RAW / "chirps_climatology_stack_1981_present_oct27_nov04_ca5.tif"
BOUNDARY_PATH = DATA_OUT / "municipalities_adm2_analytical.geojson"

COUNTRIES = {
    "BLZ": "Belize",
    "GTM": "Guatemala",
    "SLV": "El Salvador",
    "HND": "Honduras",
    "NIC": "Nicaragua",
}
COUNTRY_ORDER = ["BLZ", "GTM", "SLV", "HND", "NIC"]
REGION_CODE = "REGION"
REGION_LABEL = "Five-country region"
DATES = pd.date_range("1998-10-27", "1998-11-04", freq="D")

TREAT_RED = "#c9281d"
LIGHT_RED = "#f7b7ab"
CLIM_GRAY = "#404040"
GRID_GRAY = "#e5e5e5"
BASE_MAP_FILL = "#fff7ec"
BLUE = "#2b6cb0"
COUNTRY_COLORS = {
    "BLZ": "#7f8c8d",
    "GTM": "#4c78a8",
    "SLV": "#72a0c1",
    "HND": TREAT_RED,
    "NIC": "#8c6d5c",
    REGION_CODE: "#111111",
}
GEOD = Geod(ellps="WGS84")
SUPERSAMPLE = 8


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.labelsize": 10,
            "axes.edgecolor": "#333333",
            "axes.linewidth": 0.8,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def save_figure(fig: plt.Figure, filename: str) -> None:
    for directory in [FIGURE_OUT, OVERLEAF_OUT]:
        directory.mkdir(parents=True, exist_ok=True)
        fig.savefig(directory / filename, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def add_note(fig: plt.Figure, text: str, y: float = 0.01) -> None:
    fig.text(0.01, y, text, ha="left", va="bottom", fontsize=8, color="#444444", wrap=True)


def clean_axes(ax: plt.Axes, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID_GRAY, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)


def country_geometries() -> gpd.GeoDataFrame:
    boundaries = gpd.read_file(BOUNDARY_PATH).to_crs("EPSG:4326")
    selected = boundaries.loc[boundaries["country_name"].isin(COUNTRIES)].copy()
    if set(selected["country_name"].unique()) != set(COUNTRIES):
        missing = set(COUNTRIES) - set(selected["country_name"].unique())
        raise ValueError(f"Missing selected countries from municipality boundaries: {sorted(missing)}")
    countries = selected.dissolve(by="country_name", as_index=False)[["country_name", "geometry"]]
    countries["country_label"] = countries["country_name"].map(COUNTRIES)
    region = gpd.GeoDataFrame(
        {
            "country_name": [REGION_CODE],
            "country_label": [REGION_LABEL],
            "geometry": [countries.geometry.union_all()],
        },
        crs=countries.crs,
    )
    return pd.concat([countries, region], ignore_index=True)


def fractional_mask(geometry, shape: tuple[int, int], transform: Affine) -> np.ndarray:
    height, width = shape
    high_shape = (height * SUPERSAMPLE, width * SUPERSAMPLE)
    high_transform = transform * Affine.scale(1 / SUPERSAMPLE, 1 / SUPERSAMPLE)
    high = rasterize(
        [(geometry, 1)],
        out_shape=high_shape,
        transform=high_transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    )
    return high.reshape(height, SUPERSAMPLE, width, SUPERSAMPLE).mean(axis=(1, 3))


def geodesic_cell_areas_km2(shape: tuple[int, int], transform: Affine) -> np.ndarray:
    height, width = shape
    row_areas = np.zeros(height, dtype=float)
    for row in range(height):
        west, north = transform * (0, row)
        east, south = transform * (1, row + 1)
        area, _ = GEOD.polygon_area_perimeter(
            [west, east, east, west],
            [north, north, south, south],
        )
        row_areas[row] = abs(area) / 1_000_000
    return np.repeat(row_areas[:, None], width, axis=1)


def read_stacks() -> tuple[np.ndarray, np.ndarray, Affine, str]:
    with rasterio.open(MITCH_PATH) as mitch_src, rasterio.open(CLIM_PATH) as clim_src:
        if (
            mitch_src.shape != clim_src.shape
            or mitch_src.transform != clim_src.transform
            or mitch_src.crs != clim_src.crs
            or mitch_src.count != len(DATES)
            or clim_src.count != len(DATES)
        ):
            raise ValueError("Mitch and climatology stacks are not aligned nine-band rasters.")
        mitch = mitch_src.read().astype(float)
        climatology = clim_src.read().astype(float)
        return mitch, climatology, mitch_src.transform, str(mitch_src.crs)


def aggregate_rainfall(
    countries: gpd.GeoDataFrame,
    mitch: np.ndarray,
    climatology: np.ndarray,
    transform: Affine,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    cell_area = geodesic_cell_areas_km2(mitch.shape[1:], transform)
    valid = np.isfinite(mitch).all(axis=0) & np.isfinite(climatology).all(axis=0)
    daily_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    masks: dict[str, np.ndarray] = {}

    for row in countries.itertuples(index=False):
        code = row.country_name
        label = row.country_label
        fraction = fractional_mask(row.geometry, mitch.shape[1:], transform)
        weights = fraction * cell_area * valid
        masks[code] = fraction
        denominator = weights.sum()
        if denominator <= 0:
            raise ValueError(f"No valid CHIRPS land pixels for {label}.")

        mitch_daily = np.array([np.nansum(mitch[day] * weights) / denominator for day in range(len(DATES))])
        clim_daily = np.array(
            [np.nansum(climatology[day] * weights) / denominator for day in range(len(DATES))]
        )
        anomaly_daily = mitch_daily - clim_daily
        mitch_volume_daily = np.array(
            [np.nansum(mitch[day] * weights) * 1e-6 for day in range(len(DATES))]
        )
        clim_volume_daily = np.array(
            [np.nansum(climatology[day] * weights) * 1e-6 for day in range(len(DATES))]
        )

        for date, actual, expected, anomaly, actual_volume, expected_volume in zip(
            DATES,
            mitch_daily,
            clim_daily,
            anomaly_daily,
            mitch_volume_daily,
            clim_volume_daily,
        ):
            daily_rows.append(
                {
                    "country_code": code,
                    "country": label,
                    "date": date.date().isoformat(),
                    "mitch_mean_mm": actual,
                    "climatology_mean_mm": expected,
                    "excess_mean_mm": anomaly,
                    "mitch_volume_km3": actual_volume,
                    "climatology_volume_km3": expected_volume,
                    "excess_volume_km3": actual_volume - expected_volume,
                    "land_area_km2": denominator,
                }
            )

        total_actual = mitch_daily.sum()
        total_expected = clim_daily.sum()
        total_excess = anomaly_daily.sum()
        actual_volume = mitch_volume_daily.sum()
        expected_volume = clim_volume_daily.sum()
        summary_rows.append(
            {
                "country_code": code,
                "country": label,
                "land_area_km2": denominator,
                "mitch_total_mean_mm": total_actual,
                "climatology_total_mean_mm": total_expected,
                "excess_total_mean_mm": total_excess,
                "mitch_to_climatology_ratio": total_actual / total_expected,
                "mitch_volume_km3": actual_volume,
                "climatology_volume_km3": expected_volume,
                "excess_volume_km3": actual_volume - expected_volume,
            }
        )

    daily = pd.DataFrame(daily_rows)
    summary = pd.DataFrame(summary_rows)
    return daily, summary, masks


def daily_profile_figure(daily: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.25), sharey=True)
    for ax, code, panel in zip(
        axes,
        ["HND", REGION_CODE],
        ["A. Honduras", "B. Five-country region"],
    ):
        sub = daily.loc[daily["country_code"].eq(code)].copy()
        x = np.arange(len(sub))
        actual = sub["mitch_mean_mm"].to_numpy()
        expected = sub["climatology_mean_mm"].to_numpy()
        ax.fill_between(x, expected, actual, where=actual >= expected, color=LIGHT_RED, alpha=0.55)
        ax.plot(x, actual, color=TREAT_RED, linewidth=2.4, marker="o", markersize=4.5, label="Mitch 1998")
        ax.plot(
            x,
            expected,
            color=CLIM_GRAY,
            linewidth=1.8,
            marker="o",
            markersize=3.5,
            label="Daily climatology",
        )
        ax.set_title(panel, loc="left", fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([pd.Timestamp(value).strftime("%b %d") for value in sub["date"]], rotation=45)
        ax.set_xlabel("Date")
        clean_axes(ax)
    axes[0].set_ylabel("Area-weighted daily precipitation (mm)")
    handles = [
        Line2D([0], [0], color=TREAT_RED, marker="o", linewidth=2.4, label="Mitch 1998"),
        Line2D([0], [0], color=CLIM_GRAY, marker="o", linewidth=1.8, label="Daily climatology"),
        Patch(facecolor=LIGHT_RED, alpha=0.55, edgecolor="none", label="Excess above climatology"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.94))
    fig.suptitle("Mitch produced an exceptional nine-day rainfall sequence", y=1.01, fontsize=15, fontweight="bold")
    add_note(
        fig,
        "Notes: Country and regional values are land-area-weighted CHIRPS means. The comparison is the supplied "
        "1981-present calendar-day climatology for October 27-November 4. Shading is Mitch rainfall minus climatology.",
    )
    fig.subplots_adjust(top=0.82, bottom=0.22, wspace=0.14)
    save_figure(fig, "01_daily_rainfall_honduras_region.png")


def cumulative_profile_figure(daily: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.25), sharey=True)
    for ax, code, panel in zip(
        axes,
        ["HND", REGION_CODE],
        ["A. Honduras", "B. Five-country region"],
    ):
        sub = daily.loc[daily["country_code"].eq(code)].copy()
        x = np.arange(len(sub))
        actual = sub["mitch_mean_mm"].cumsum().to_numpy()
        expected = sub["climatology_mean_mm"].cumsum().to_numpy()
        ax.fill_between(x, expected, actual, color=LIGHT_RED, alpha=0.55)
        ax.plot(x, actual, color=TREAT_RED, linewidth=2.5, marker="o", markersize=4)
        ax.plot(x, expected, color=CLIM_GRAY, linewidth=1.8, marker="o", markersize=3)
        ax.annotate(
            f"{actual[-1]:.0f} mm",
            (x[-1], actual[-1]),
            xytext=(-5, 8),
            textcoords="offset points",
            ha="right",
            color=TREAT_RED,
            fontweight="bold",
        )
        ax.annotate(
            f"{expected[-1]:.0f} mm",
            (x[-1], expected[-1]),
            xytext=(-5, -15),
            textcoords="offset points",
            ha="right",
            color=CLIM_GRAY,
        )
        ax.text(
            0.03,
            0.91,
            f"Excess: {actual[-1] - expected[-1]:.0f} mm",
            transform=ax.transAxes,
            color=TREAT_RED,
            fontweight="bold",
            bbox={"facecolor": "white", "edgecolor": LIGHT_RED, "boxstyle": "round,pad=0.3"},
        )
        ax.set_title(panel, loc="left", fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([pd.Timestamp(value).strftime("%b %d") for value in sub["date"]], rotation=45)
        ax.set_xlabel("Date")
        clean_axes(ax)
    axes[0].set_ylabel("Cumulative area-weighted precipitation (mm)")
    fig.suptitle("The rainfall surplus accumulated throughout Mitch's passage", y=0.98, fontsize=15, fontweight="bold")
    add_note(
        fig,
        "Notes: Lines cumulate the area-weighted daily depth. The vertical distance between the lines is the cumulative "
        "rainfall anomaly relative to the supplied calendar-day climatology.",
    )
    fig.subplots_adjust(top=0.84, bottom=0.22, wspace=0.14)
    save_figure(fig, "02_cumulative_rainfall_honduras_region.png")


def country_depth_figure(summary: pd.DataFrame) -> None:
    country = summary.loc[summary["country_code"].isin(COUNTRY_ORDER)].copy()
    country["order"] = country["country_code"].map({code: i for i, code in enumerate(COUNTRY_ORDER)})
    country = country.sort_values("order", ascending=False)
    y = np.arange(len(country))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.25), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axes[0]
    for idx, row in enumerate(country.itertuples(index=False)):
        ax.plot(
            [row.climatology_total_mean_mm, row.mitch_total_mean_mm],
            [idx, idx],
            color=LIGHT_RED if row.country_code == "HND" else "#bdbdbd",
            linewidth=5,
            solid_capstyle="round",
            zorder=1,
        )
        ax.scatter(row.climatology_total_mean_mm, idx, color=CLIM_GRAY, s=42, zorder=3)
        ax.scatter(
            row.mitch_total_mean_mm,
            idx,
            color=COUNTRY_COLORS[row.country_code],
            s=68 if row.country_code == "HND" else 54,
            zorder=4,
        )
        ax.text(
            row.mitch_total_mean_mm + 5,
            idx,
            f"+{row.excess_total_mean_mm:.0f} mm",
            va="center",
            color=COUNTRY_COLORS[row.country_code],
            fontweight="bold" if row.country_code == "HND" else "normal",
        )
    ax.set_yticks(y)
    ax.set_yticklabels(country["country"])
    for tick, code in zip(ax.get_yticklabels(), country["country_code"]):
        if code == "HND":
            tick.set_fontweight("bold")
            tick.set_color(TREAT_RED)
    ax.set_xlabel("Nine-day area-weighted precipitation (mm)")
    ax.set_title("A. Expected and observed rainfall", loc="left", fontweight="bold")
    clean_axes(ax, "x")

    ax = axes[1]
    colors = [COUNTRY_COLORS[code] for code in country["country_code"]]
    ax.barh(y, country["mitch_to_climatology_ratio"], color=colors, alpha=0.9)
    ax.axvline(1, color=CLIM_GRAY, linewidth=1.2, linestyle="--")
    for idx, value in enumerate(country["mitch_to_climatology_ratio"]):
        ax.text(value + 0.05, idx, f"{value:.1f}x", va="center", color=colors[idx], fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels([])
    ax.set_xlabel("Mitch total / climatological total")
    ax.set_title("B. Multiple of climatology", loc="left", fontweight="bold")
    clean_axes(ax, "x")

    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=CLIM_GRAY, label="Climatology", markersize=7),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=TREAT_RED, label="Mitch total", markersize=8),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.94))
    fig.suptitle("Every sample country received substantially more rain than normal", y=1.01, fontsize=15, fontweight="bold")
    add_note(
        fig,
        "Notes: Totals sum October 27-November 4 daily precipitation. The left-panel labels report excess millimeters; "
        "the right panel scales Mitch rainfall by the same-date climatological total.",
    )
    fig.subplots_adjust(top=0.82, bottom=0.18, wspace=0.12)
    save_figure(fig, "03_country_total_excess_comparison.png")


def spatial_map_figure(
    countries: gpd.GeoDataFrame,
    mitch: np.ndarray,
    climatology: np.ndarray,
    masks: dict[str, np.ndarray],
    transform: Affine,
) -> None:
    region_mask = masks[REGION_CODE]
    actual = mitch.sum(axis=0)
    anomaly = actual - climatology.sum(axis=0)
    actual = np.where(region_mask > 0.01, actual, np.nan)
    anomaly = np.where(region_mask > 0.01, anomaly, np.nan)
    extent = [
        transform.c,
        transform.c + transform.a * actual.shape[1],
        transform.f + transform.e * actual.shape[0],
        transform.f,
    ]
    selected = countries.loc[countries["country_name"].isin(COUNTRY_ORDER)].copy()
    actual_limits = np.nanpercentile(actual, [2, 98])
    abs_limit = np.nanpercentile(np.abs(anomaly), 98)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8), constrained_layout=False)
    im0 = axes[0].imshow(
        actual,
        extent=extent,
        origin="upper",
        cmap="Blues",
        vmin=max(0, actual_limits[0]),
        vmax=actual_limits[1],
        interpolation="nearest",
    )
    im1 = axes[1].imshow(
        anomaly,
        extent=extent,
        origin="upper",
        cmap="RdBu_r",
        norm=TwoSlopeNorm(vmin=-abs_limit, vcenter=0, vmax=abs_limit),
        interpolation="nearest",
    )
    for ax, title in zip(
        axes,
        ["A. Mitch storm-total rainfall", "B. Excess relative to climatology"],
    ):
        selected.boundary.plot(ax=ax, color="#222222", linewidth=0.8)
        hnd = selected.loc[selected["country_name"].eq("HND")]
        hnd.boundary.plot(ax=ax, color=TREAT_RED, linewidth=1.8)
        for row in selected.itertuples(index=False):
            point = row.geometry.representative_point()
            ax.text(
                point.x,
                point.y,
                row.country_name,
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color="#111111",
                bbox={"facecolor": "white", "alpha": 0.55, "edgecolor": "none", "pad": 1},
            )
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlim(-92.3, -82.7)
        ax.set_ylim(10.7, 18.5)
        ax.set_axis_off()
    cbar0 = fig.colorbar(im0, ax=axes[0], orientation="horizontal", fraction=0.047, pad=0.025)
    cbar0.set_label("Rainfall (mm)")
    cbar1 = fig.colorbar(im1, ax=axes[1], orientation="horizontal", fraction=0.047, pad=0.025)
    cbar1.set_label("Rainfall anomaly (mm)")
    fig.suptitle("Mitch's rainfall surplus varied sharply across the region", y=0.98, fontsize=15, fontweight="bold")
    add_note(
        fig,
        "Notes: Raster cells show October 27-November 4 totals. Panel B subtracts the supplied same-calendar-day "
        "climatology cell by cell. Color limits trim the outer 2 percent for legibility; underlying calculations are untrimmed.",
    )
    fig.subplots_adjust(top=0.88, bottom=0.12, wspace=0.05)
    save_figure(fig, "04_spatial_total_and_excess_map.png")


def exceedance_figure(
    summary: pd.DataFrame,
    mitch: np.ndarray,
    climatology: np.ndarray,
    masks: dict[str, np.ndarray],
    transform: Affine,
) -> None:
    anomaly = mitch.sum(axis=0) - climatology.sum(axis=0)
    cell_area = geodesic_cell_areas_km2(anomaly.shape, transform)
    thresholds = np.arange(0, 451, 25)

    fig, ax = plt.subplots(figsize=(9.6, 5.6))
    for code in COUNTRY_ORDER + [REGION_CODE]:
        weights = masks[code] * cell_area * np.isfinite(anomaly)
        denominator = weights.sum()
        shares = np.array([(weights * (anomaly >= threshold)).sum() / denominator * 100 for threshold in thresholds])
        if code == "HND":
            linewidth, alpha, zorder = 3.0, 1.0, 5
        elif code == REGION_CODE:
            linewidth, alpha, zorder = 2.1, 1.0, 4
        else:
            linewidth, alpha, zorder = 1.4, 0.78, 2
        label = COUNTRIES.get(code, REGION_LABEL)
        ax.plot(
            thresholds,
            shares,
            color=COUNTRY_COLORS[code],
            linewidth=linewidth,
            alpha=alpha,
            label=label,
            zorder=zorder,
        )
    ax.axhline(50, color="#777777", linestyle=":", linewidth=1)
    ax.set_xlabel("Storm-total rainfall anomaly threshold (mm)")
    ax.set_ylabel("Share of land area above threshold (%)")
    ax.set_xlim(thresholds.min(), thresholds.max())
    ax.set_ylim(0, 102)
    ax.set_title("How geographically widespread was Mitch's excess rainfall?", loc="left", fontweight="bold", fontsize=15)
    clean_axes(ax)
    ax.legend(loc="upper right", frameon=True, framealpha=0.95, ncol=2)
    hnd = summary.loc[summary["country_code"].eq("HND")].iloc[0]
    ax.text(
        0.02,
        0.08,
        f"Honduras mean excess: {hnd['excess_total_mean_mm']:.0f} mm",
        transform=ax.transAxes,
        color=TREAT_RED,
        fontweight="bold",
        bbox={"facecolor": "white", "edgecolor": LIGHT_RED, "boxstyle": "round,pad=0.3"},
    )
    add_note(
        fig,
        "Notes: Each curve reports the area-weighted share of national land whose nine-day CHIRPS total exceeded the "
        "same-date climatology by at least the horizontal-axis amount. Curves use untrimmed raster-cell anomalies.",
    )
    fig.subplots_adjust(bottom=0.17)
    save_figure(fig, "05_excess_rainfall_land_area_curves.png")


def water_volume_figure(summary: pd.DataFrame) -> None:
    country = summary.loc[summary["country_code"].isin(COUNTRY_ORDER)].copy()
    country["order"] = country["country_code"].map({code: i for i, code in enumerate(COUNTRY_ORDER)})
    country = country.sort_values("order")
    x = np.arange(len(country))
    expected = country["climatology_volume_km3"].to_numpy()
    excess = country["excess_volume_km3"].to_numpy()
    colors = [COUNTRY_COLORS[code] for code in country["country_code"]]

    fig, ax = plt.subplots(figsize=(9.6, 5.5))
    ax.bar(x, expected, color="#bdbdbd", label="Climatological volume", zorder=2)
    ax.bar(x, excess, bottom=expected, color=colors, label="Excess during Mitch", zorder=2)
    for idx, (base, extra, code) in enumerate(zip(expected, excess, country["country_code"])):
        ax.text(
            idx,
            base + extra + max(country["mitch_volume_km3"]) * 0.025,
            f"+{extra:.1f} km³",
            ha="center",
            color=COUNTRY_COLORS[code],
            fontweight="bold" if code == "HND" else "normal",
        )
    ax.set_xticks(x)
    ax.set_xticklabels(country["country"])
    for tick, code in zip(ax.get_xticklabels(), country["country_code"]):
        if code == "HND":
            tick.set_fontweight("bold")
            tick.set_color(TREAT_RED)
    ax.set_ylabel("Rainfall water volume over land (km³)")
    clean_axes(ax)
    handles = [
        Patch(facecolor="#bdbdbd", label="Climatological volume"),
        Patch(facecolor=TREAT_RED, label="Excess during Mitch"),
    ]
    ax.legend(handles=handles, loc="upper left", frameon=False)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.1615)
    save_figure(fig, "06_excess_precipitation_water_volume.png")


def write_notes(summary: pd.DataFrame) -> None:
    lookup = summary.set_index("country_code")
    hnd = lookup.loc["HND"]
    region = lookup.loc[REGION_CODE]
    text = f"""# CHIRPS descriptive precipitation figures

These figures compare the supplied October 27-November 4, 1998 CHIRPS daily stack with the
supplied 1981-present same-calendar-day climatology stack.

Key area-weighted results:

- Honduras: {hnd['mitch_total_mean_mm']:.1f} mm during Mitch versus
  {hnd['climatology_total_mean_mm']:.1f} mm climatologically, an excess of
  {hnd['excess_total_mean_mm']:.1f} mm ({hnd['mitch_to_climatology_ratio']:.2f} times normal).
- Five-country region: {region['mitch_total_mean_mm']:.1f} mm during Mitch versus
  {region['climatology_total_mean_mm']:.1f} mm climatologically, an excess of
  {region['excess_total_mean_mm']:.1f} mm ({region['mitch_to_climatology_ratio']:.2f} times normal).
- Honduras excess rainfall volume: {hnd['excess_volume_km3']:.2f} cubic kilometers.
- Five-country excess rainfall volume: {region['excess_volume_km3']:.2f} cubic kilometers.

Interpretation: “excess” is a descriptive departure from the supplied calendar-day climatological
mean. It is not a return-period estimate, a causal flood measure, or observed runoff.
"""
    (FIGURE_OUT / "README.md").write_text(text, encoding="utf-8")


def validate_outputs(daily: pd.DataFrame, summary: pd.DataFrame) -> None:
    if len(daily) != (len(COUNTRY_ORDER) + 1) * len(DATES):
        raise AssertionError("Unexpected number of country-date rainfall rows.")
    if len(summary) != len(COUNTRY_ORDER) + 1:
        raise AssertionError("Unexpected number of country rainfall summaries.")
    if not (summary["mitch_total_mean_mm"] > summary["climatology_total_mean_mm"]).all():
        raise AssertionError("At least one country aggregate does not show positive excess rainfall.")
    expected = {
        "01_daily_rainfall_honduras_region.png",
        "02_cumulative_rainfall_honduras_region.png",
        "03_country_total_excess_comparison.png",
        "04_spatial_total_and_excess_map.png",
        "05_excess_rainfall_land_area_curves.png",
        "06_excess_precipitation_water_volume.png",
    }
    for directory in [FIGURE_OUT, OVERLEAF_OUT]:
        missing = [name for name in expected if not (directory / name).exists()]
        if missing:
            raise AssertionError(f"Missing CHIRPS outputs from {directory}: {missing}")


def main() -> None:
    configure_style()
    countries = country_geometries()
    mitch, climatology, transform, raster_crs = read_stacks()
    if raster_crs != "EPSG:4326":
        countries = countries.to_crs(raster_crs)
    daily, summary, masks = aggregate_rainfall(countries, mitch, climatology, transform)

    DATA_OUT.mkdir(parents=True, exist_ok=True)
    FIGURE_OUT.mkdir(parents=True, exist_ok=True)
    daily.to_csv(DATA_OUT / "chirps_mitch_daily_country_summary.csv", index=False)
    summary.to_csv(DATA_OUT / "chirps_mitch_country_summary.csv", index=False)

    daily_profile_figure(daily)
    cumulative_profile_figure(daily)
    country_depth_figure(summary)
    spatial_map_figure(countries, mitch, climatology, masks, transform)
    exceedance_figure(summary, mitch, climatology, masks, transform)
    water_volume_figure(summary)
    write_notes(summary)
    validate_outputs(daily, summary)

    print(summary.round(3).to_string(index=False))
    print(f"Wrote six CHIRPS figures to {FIGURE_OUT} and {OVERLEAF_OUT}")


if __name__ == "__main__":
    main()
