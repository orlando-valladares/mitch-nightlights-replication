from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = ROOT / "working" / "scripts" / "pipeline_engine.py"


def load_engine():
    spec = importlib.util.spec_from_file_location("draft_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    engine = load_engine()
    engine.ensure_dirs()
    engine.ensure_structured_dirs()
    ebtrk = engine.load_mitch_ebtrk()
    munis = engine.attach_audited_ebtrk_exposures(engine.load_municipalities())
    attrs = engine.WORKING / "data" / "processed" / "municipality_attributes.csv"
    panel_path = engine.WORKING / "data" / "processed" / "analysis_panel_main.csv"
    assignment = engine.pd.read_csv(attrs) if attrs.exists() else engine.build_assignment(munis)
    panel = engine.pd.read_csv(panel_path) if panel_path.exists() else engine.build_panel(assignment)
    engine.write_reader_summary_table(assignment)
    engine.write_expanded_summary_table(assignment)
    engine.plot_mitch_intro_map(munis, ebtrk)
    engine.plot_structured_exposure_maps(munis, ebtrk)
    engine.plot_ntl_maps(munis)
    engine.write_structured_regression_tables(panel)

    dynamic_paths = [
        engine.PAPER_LEGACY / "main_results" / "figures" / "dynamic_did" / "no_year_fe" / "fig_four_treatments_no34.png",
        engine.OUT / "results" / "figures" / "structured" / "legacy" / "main_results" / "figures" / "dynamic_did" / "no_year_fe" / "fig_four_treatments_no34.png",
    ]
    for path in dynamic_paths:
        engine.plot_dynamic_measure(
            panel,
            engine.FOUR_TREATMENT_MEASURES,
            "Dynamic DiD: Unit FE",
            path,
            prefilter=False,
            year_fe=False,
        )

    event_paths = [
        engine.PAPER / "main_results" / "figures" / "event_study" / "year_fe_ntl_filter" / "fig_four_treatments_no34.png",
        engine.OUT / "results" / "figures" / "structured" / "main_results" / "figures" / "event_study" / "year_fe_ntl_filter" / "fig_four_treatments_no34.png",
    ]
    for path in event_paths:
        engine.plot_event_measure(
            panel,
            engine.FOUR_TREATMENT_MEASURES,
            "Event study: Unit + Year FE for pre-Mitch NTL median",
            path,
            year_fe=True,
            prefilter=True,
        )

    broad_paths = [
        engine.PAPER / "main_results" / "figures" / "event_study" / "year_fe_ntl_filter" / "fig_34kt.png",
        engine.OUT / "results" / "figures" / "structured" / "main_results" / "figures" / "event_study" / "year_fe_ntl_filter" / "fig_34kt.png",
    ]
    for path in broad_paths:
        engine.plot_event_measure(
            panel,
            [engine.MEASURES[2]],
            "Event study: Unit + Year FE for pre-Mitch NTL median",
            path,
            year_fe=True,
            prefilter=True,
        )

    engine.write_single_year_outputs(panel)
    engine.create_recovery_hypotheses_figure()
    print("Built final-paper tables, figures, and maps")


if __name__ == "__main__":
    main()
