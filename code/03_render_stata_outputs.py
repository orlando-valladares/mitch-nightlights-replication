"""Render native Stata estimates with the project's existing visual design.

This file performs no estimation. It reads the CSV written by
``code/02_estimate_mitch.do`` and passes those estimates to the established
table and figure formatters.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "working" / "scripts" / "pipeline_engine.py"
RESULTS_PATH = ROOT / "out" / "results" / "stata" / "mitch_event_study_results.csv"
OVERLEAF_FIGURES = ROOT / "working" / "overleaf" / "Paper_Figures"


def load_engine():
    sys.path.insert(0, str(ENGINE_PATH.parent))
    spec = importlib.util.spec_from_file_location("stata_render_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TREATMENT_SLUGS = {
    "ebtrk_treat50_r64_all": ("64kt", "municipal"),
    "ebtrk_treat50_r50_all": ("50kt", "municipal"),
    "ebtrk_treat50_r34_all": ("34kt", "municipal"),
    "chirps_max_anomaly_top10": ("rain_top10", "municipal"),
    "rain50_chirps_top10": ("wind50_rain_top10", "municipal"),
    "death_pc_top10_state": ("deaths_top10", "state"),
}


def select_results(
    results: pd.DataFrame,
    model: str,
    treatment_column: str,
    prefilter: bool,
    year_fe: bool,
) -> pd.DataFrame:
    if treatment_column not in TREATMENT_SLUGS:
        raise KeyError(f"No Stata result mapping for {treatment_column}")
    treatment, panel = TREATMENT_SLUGS[treatment_column]
    sample = "median" if prefilter else "all"
    selected = results.loc[
        results["model"].eq(model)
        & results["treatment"].eq(treatment)
        & results["panel"].eq(panel)
        & results["sample"].eq(sample)
        & results["year_fe"].eq(int(year_fe))
    ].copy()
    if selected.empty:
        raise RuntimeError(
            f"Missing Stata result: model={model}, treatment={treatment}, "
            f"panel={panel}, sample={sample}, year_fe={year_fe}"
        )
    return selected.sort_values(["period_start", "period_end"]).reset_index(drop=True)


def sync_to_overleaf(relative_paths: list[Path]) -> None:
    for relative in relative_paths:
        source = ROOT / "paper" / "Paper_Figures" / relative
        destination = OVERLEAF_FIGURES / relative
        if not source.exists():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    if not RESULTS_PATH.exists():
        raise FileNotFoundError(
            f"Run 'stata -b do code/00_master.do' first; missing {RESULTS_PATH}"
        )

    results = pd.read_csv(RESULTS_PATH)
    engine = load_engine()

    def stata_event_period_coefficients(
        panel: pd.DataFrame,
        treat_col: str,
        prefilter: bool,
        year_fe: bool,
        binary: bool = True,
    ) -> pd.DataFrame:
        del panel, binary
        selected = select_results(results, "twoyear", treat_col, prefilter, year_fe)
        selected["period"] = selected.apply(
            lambda row: engine.period_label(int(row.period_start), int(row.period_end)), axis=1
        )
        selected["x"] = (selected["period_start"] + selected["period_end"]) / 2
        selected["coef"] = selected["coefficient"]
        selected["se"] = selected["std_error"]
        selected["p"] = selected["p_value"]
        selected["lb"] = selected["ci_low"]
        selected["ub"] = selected["ci_high"]
        selected["reference"] = (
            selected["period_start"].eq(1996) & selected["period_end"].eq(1997)
        ).astype(int)
        return selected[
            ["period_start", "period_end", "period", "x", "coef", "se", "p", "lb", "ub", "reference"]
        ]

    def stata_event_coefficients(
        panel: pd.DataFrame,
        treat_col: str,
        prefilter: bool,
        year_fe: bool,
    ) -> pd.DataFrame:
        del panel
        selected = select_results(results, "annual", treat_col, prefilter, year_fe)
        selected["year"] = selected["period_start"].astype(int)
        selected["coef"] = selected["coefficient"]
        selected["se"] = selected["std_error"]
        selected["p"] = selected["p_value"]
        selected["lb"] = selected["ci_low"]
        selected["ub"] = selected["ci_high"]
        selected["reference"] = selected["year"].eq(1997).astype(int)
        return selected[["year", "coef", "se", "p", "lb", "ub", "reference"]]

    def stata_run_did(
        panel: pd.DataFrame,
        treat_col: str,
        measure: str,
        sample_label: str,
        year_fe: bool,
        continuous: bool = False,
    ):
        del panel, continuous
        prefilter = "pre-Mitch" in sample_label
        selected = select_results(results, "did", treat_col, prefilter, year_fe)
        row = selected.iloc[0]
        return engine.RegressionResult(
            measure=measure,
            sample=sample_label,
            year_fe=year_fe,
            coef=float(row.coefficient),
            se=float(row.std_error),
            p=float(row.p_value),
            n=int(row.observations),
            r2=np.nan,
            treated_units=float(row.treated_units),
            control_units=float(row.control_units),
        )

    engine.event_period_coefficients = stata_event_period_coefficients
    engine.event_coefficients = stata_event_coefficients
    engine.event_series = lambda panel, treat_col, continuous, prefilter, year_fe: (
        stata_event_coefficients(panel, treat_col, prefilter, year_fe)
    )
    engine.run_did = stata_run_did

    panel = pd.read_csv(ROOT / "working" / "data" / "processed" / "analysis_panel_main.csv")
    engine.ensure_dirs()
    engine.ensure_structured_dirs()
    engine.write_ebtrk_event_table(panel)
    engine.write_structured_regression_tables(panel)

    event_specs = engine.MEASURES[:5] + [
        {
            "slug": "four_treatments_no34",
            "label": "Four treatments excluding 34 kt",
            "col": "",
            "binary": True,
        }
    ]
    for spec in event_specs:
        specs = engine.FOUR_TREATMENT_MEASURES if spec["slug"] == "four_treatments_no34" else [spec]
        for base in [
            engine.PAPER / "main_results" / "figures" / "event_study" / "year_fe_ntl_filter",
            engine.OUT
            / "results"
            / "figures"
            / "structured"
            / "main_results"
            / "figures"
            / "event_study"
            / "year_fe_ntl_filter",
        ]:
            engine.plot_event_measure(
                panel,
                specs,
                "Event study: Unit + Year FE for pre-Mitch NTL median",
                base / f"fig_{spec['slug']}.png",
                year_fe=True,
                prefilter=True,
            )

    engine.write_single_year_outputs(panel)

    overleaf_paths = [
        Path("main_results/figures/event_study/year_fe_ntl_filter/fig_four_treatments_no34.png"),
        Path("main_results/figures/event_study/year_fe_ntl_filter/fig_34kt.png"),
        Path("main_results/regression_tables/event_study/table_four_treatments_no34.tex"),
        Path("single_years/eventstudy_annual_four_treatments_no34.png"),
        Path("single_years/regression_table_four_treatments_no34.tex"),
        Path("appendix/regression_tables/table_four_treatments_no34_unit_fe.tex"),
    ]
    sync_to_overleaf(overleaf_paths)

    print(f"Rendered {len(results):,} native Stata result rows using the existing visual styles.")


if __name__ == "__main__":
    main()
