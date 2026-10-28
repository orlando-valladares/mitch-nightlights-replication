from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"

EXPECTED_CENSUS = {
    ("refrigerator", "treated_x_2001"): (0.03088, 0.04785),
    ("refrigerator", "treated_x_2013"): (0.06731, 0.07462),
    ("television", "treated_x_2001"): (0.09074, 0.07273),
    ("television", "treated_x_2013"): (0.20837, 0.08809),
}


def verify_paper_references() -> None:
    main = (PAPER / "main.tex").read_text(encoding="utf-8")
    references = []
    references.extend(re.findall(r"\\input\{([^}]+)\}", main))
    references.extend(
        re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", main)
    )
    missing = [reference for reference in references if not (PAPER / reference).exists()]
    if missing:
        formatted = "\n".join(f"  - {reference}" for reference in missing)
        raise AssertionError(f"Missing paper assets:\n{formatted}")


def verify_census_results() -> None:
    path = (
        ROOT
        / "out"
        / "results"
        / "tables"
        / "structured"
        / "appendix"
        / "census"
        / "normal_goods_estimates.csv"
    )
    results = pd.read_csv(path).set_index(["measure", "term"])
    for key, (expected_coefficient, expected_se) in EXPECTED_CENSUS.items():
        row = results.loc[key]
        if abs(row["estimate"] - expected_coefficient) > 5e-5:
            raise AssertionError(f"Unexpected coefficient for {key}: {row['estimate']}")
        if abs(row["std_error"] - expected_se) > 5e-5:
            raise AssertionError(f"Unexpected standard error for {key}: {row['std_error']}")


def verify_filter_value() -> None:
    table = (
        PAPER
        / "Paper_Figures"
        / "data"
        / "summary_tables"
        / "table_exposure_summary_reader.tex"
    ).read_text(encoding="utf-8")
    if "101.79" not in table:
        raise AssertionError("Table 1 does not report the pre-Mitch median of 101.79.")


def main() -> None:
    verify_paper_references()
    verify_census_results()
    verify_filter_value()
    print("Replication output verification passed")


if __name__ == "__main__":
    main()
