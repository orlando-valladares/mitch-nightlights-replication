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
    engine.build_summary_tables(assignment)
    engine.write_raw_mahajan_summary()
    engine.plot_ebtrk_maps(munis, ebtrk)
    engine.plot_expanded_maps(munis, ebtrk)
    engine.plot_results(panel)
    engine.plot_expanded_result_figures(panel)
    engine.copy_existing_support_files()
    engine.build_structured_outputs(munis, ebtrk, assignment, panel)
    print("Built structured tables, figures, maps, and presentation")


if __name__ == "__main__":
    main()
