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
    ntl = engine.pd.read_csv(engine.WORKING / "data" / "processed" / "did_dashboard" / "ntl_municipality_year_panel.csv")
    ntl["stable_sum"] = engine.pd.to_numeric(ntl["stable_sum"], errors="coerce")
    ntl["log_ntl"] = engine.np.log1p(ntl["stable_sum"])
    out = engine.WORKING / "data" / "processed" / "municipality_year_panel.csv"
    ntl.to_csv(out, index=False)
    print("Built municipality_year_panel.csv")


if __name__ == "__main__":
    main()
