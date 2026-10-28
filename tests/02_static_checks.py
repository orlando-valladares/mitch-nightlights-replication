from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATA_FILES = [
    ROOT / "code" / "00_master.do",
    ROOT / "code" / "01_validate_panel.do",
    ROOT / "code" / "02_estimate_mitch.do",
    ROOT / "coding-sample" / "stata_coding_sample.do",
]

for path in STATA_FILES:
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:[/\\]", text), f"Absolute drive path in {path}"
    assert "/home/" not in text, f"Absolute home path in {path}"

readme = (ROOT / "README.md").read_text(encoding="utf-8")
assert "code/00_master.do" in readme
assert "AI-assisted exploratory visualization tools" in readme

expected = [
    ROOT / "out" / "results" / "stata" / "mitch_event_study_results.csv",
    ROOT / "out" / "results" / "figures" / "structured" / "main_results"
    / "figures" / "event_study" / "year_fe_ntl_filter" / "fig_four_treatments_no34.png",
]
for path in expected:
    assert path.exists() and path.stat().st_size > 0, f"Missing output: {path}"

print("Static checks passed.")
