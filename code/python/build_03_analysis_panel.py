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
    attrs_path = engine.WORKING / "data" / "processed" / "municipality_attributes.csv"
    if attrs_path.exists():
        assignment = engine.pd.read_csv(attrs_path)
    else:
        munis = engine.attach_audited_ebtrk_exposures(engine.load_municipalities())
        assignment = engine.build_assignment(munis)
    panel = engine.build_panel(assignment)
    panel.to_csv(engine.WORKING / "data" / "processed" / "analysis_panel_main.csv", index=False)
    print("Built analysis_panel_main.csv")


if __name__ == "__main__":
    main()
