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
    panel_path = engine.WORKING / "data" / "processed" / "analysis_panel_main.csv"
    if panel_path.exists():
        panel = engine.pd.read_csv(panel_path)
    else:
        assignment = engine.pd.read_csv(engine.WORKING / "data" / "processed" / "municipality_attributes.csv")
        panel = engine.build_panel(assignment)
    engine.write_reghdfe_bridge(panel)
    engine.run_regressions(panel)
    engine.write_structured_regression_tables(panel)
    engine.write_robustness_tables(panel)
    print("Built regression outputs")


if __name__ == "__main__":
    main()
