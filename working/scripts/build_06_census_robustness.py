from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "working" / "data" / "replication_inputs" / "ipums_honduras"
PAPER = ROOT / "paper" / "Paper_Figures"
OUT = ROOT / "out" / "results"

HOUSEHOLDS = INPUT / "households.csv"
EDUCATION = INPUT / "honduras_50kt_population_education.csv"
DWELLING = INPUT / "honduras_50kt_dwelling_summary.csv"

YEARS = [1988, 2001, 2013]
CLEAN_GROUPS = {340002001, 340002003, 340015006}
MIXED_GROUPS = {340009001, 340011001}

TARGET_GROUPS = {
    340002001: ("Colon group: Balfate--Iriona", "7/7"),
    340002003: ("Colon group: Saba--Tocoa", "3/3"),
    340009001: ("Gracias a Dios group", "1/6"),
    340011001: ("Bay Islands group", "3/4"),
    340015006: ("Olancho group: Gualaco--San Esteban", "2/2"),
}

DWELLING_MEASURES = [
    ("share_electricity", "Electricity"),
    ("share_piped_water", "Piped water"),
    ("share_sewage_or_septic", "Sewer or septic"),
    ("share_wood_solid_fuel", "Wood or other solid cooking fuel"),
    ("share_earth_floor", "Earth floor"),
    ("share_masonry_wall", "Masonry wall"),
    ("share_sheet_metal_roof", "Sheet-metal roof"),
    ("share_refrigerator", "Refrigerator"),
    ("share_television", "Television"),
    ("share_more_than_3_per_room", "More than three persons per room"),
]


def classify_groups(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["clean_treated"] = result["geo2_hn"].isin(CLEAN_GROUPS).astype(float)
    result["mixed_group"] = result["geo2_hn"].isin(MIXED_GROUPS)
    return result


def wls_cluster(
    data: pd.DataFrame,
    outcome: str,
    weight: str,
    cluster: str,
    fixed_effects: list[str],
    interactions: dict[str, pd.Series],
) -> pd.DataFrame:
    frame = data.dropna(subset=[outcome, weight, cluster] + fixed_effects).copy()
    x_parts = [pd.DataFrame({"const": np.ones(len(frame))}, index=frame.index)]
    for fixed_effect in fixed_effects:
        x_parts.append(
            pd.get_dummies(
                frame[fixed_effect].astype(str),
                prefix=fixed_effect,
                drop_first=True,
                dtype=float,
            )
        )
    x_parts.append(
        pd.DataFrame(
            {name: values.loc[frame.index].astype(float) for name, values in interactions.items()}
        )
    )
    design = pd.concat(x_parts, axis=1)
    x = design.to_numpy(float)
    y = frame[outcome].to_numpy(float)
    w = frame[weight].to_numpy(float)
    xtwx_inv = np.linalg.pinv(x.T @ (w[:, None] * x), rcond=1e-10)
    beta = xtwx_inv @ (x.T @ (w * y))
    residual = y - x @ beta

    groups = frame[cluster].astype(str).to_numpy()
    unique_groups = np.unique(groups)
    meat = np.zeros((x.shape[1], x.shape[1]))
    for group in unique_groups:
        selected = groups == group
        score = x[selected].T @ (w[selected] * residual[selected])
        meat += np.outer(score, score)
    covariance = xtwx_inv @ meat @ xtwx_inv
    n, k, g = len(frame), x.shape[1], len(unique_groups)
    if g > 1 and n > k:
        covariance *= (g / (g - 1)) * ((n - 1) / (n - k))
    standard_errors = np.sqrt(np.clip(np.diag(covariance), 0, None))

    rows = []
    for name in interactions:
        position = design.columns.get_loc(name)
        rows.append(
            {
                "term": name,
                "estimate": beta[position],
                "std_error": standard_errors[position],
                "n_cells": n,
                "clusters": g,
            }
        )
    return pd.DataFrame(rows)


def build_normal_goods_results(households: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for measure in ["refrigerator", "television"]:
        data = classify_groups(households.loc[households["measure"].eq(measure)])
        use = data.loc[~data["mixed_group"]].copy()
        interactions = {
            f"treated_x_{year}": use["clean_treated"] * use["year"].eq(year).astype(float)
            for year in [2001, 2013]
        }
        estimate = wls_cluster(
            use,
            "share",
            "weight",
            "geo2_hn",
            ["geo2_hn", "year"],
            interactions,
        )
        estimate["measure"] = measure
        estimate["specification"] = "clean"
        rows.append(estimate)
    return pd.concat(rows, ignore_index=True)


def save_normal_goods_figure(results: pd.DataFrame, path: Path) -> None:
    labels = {"refrigerator": "Refrigerator", "television": "Television"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.9), constrained_layout=True)
    for ax, measure in zip(axes, ["refrigerator", "television"]):
        data = results.loc[results["measure"].eq(measure)].copy()
        data["year"] = data["term"].str.extract(r"(\d{4})").astype(int)
        reference = pd.DataFrame({"year": [1988], "estimate": [0.0], "std_error": [0.0]})
        plot = pd.concat(
            [data[["year", "estimate", "std_error"]], reference],
            ignore_index=True,
        ).sort_values("year")
        plot["lb"] = 100 * (plot["estimate"] - 1.96 * plot["std_error"])
        plot["ub"] = 100 * (plot["estimate"] + 1.96 * plot["std_error"])
        plot["coef"] = 100 * plot["estimate"]
        ax.fill_between(
            plot["year"].to_numpy(float),
            plot["lb"].to_numpy(float),
            plot["ub"].to_numpy(float),
            color="#d9d9d9",
        )
        ax.plot(
            plot["year"],
            plot["coef"],
            color="black",
            marker="o",
            markersize=3.0,
            linewidth=1.05,
        )
        ax.axhline(0, color="#777777", linewidth=0.8)
        ax.axvline(1998, color="#999999", linestyle="--", linewidth=0.8)
        ax.axvline(2000, color="#bbbbbb", linestyle=":", linewidth=0.8)
        ax.set_title(labels[measure], fontsize=10)
        ax.set_xticks(YEARS)
        ax.set_xticklabels(["1988 (ref.)", "2001", "2013"], rotation=35, ha="right", fontsize=7)
    axes[0].set_ylabel("Coefficient relative to 1988 (percentage points)", fontsize=9)
    fig.suptitle("Census normal-goods event study: group and year fixed effects", fontsize=13)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def latex_escape(value: object) -> str:
    text = str(value)
    for source, target in [
        (chr(92), chr(92) + "textbackslash{}"),
        ("&", chr(92) + "&"),
        ("%", chr(92) + "%"),
        ("_", chr(92) + "_"),
        ("#", chr(92) + "#"),
    ]:
        text = text.replace(source, target)
    return text


def normal_goods_table(results: pd.DataFrame) -> str:
    output = results.copy()
    output["Estimate"] = 100 * output["estimate"]
    output["SE"] = 100 * output["std_error"]
    output = output[
        ["specification", "measure", "term", "Estimate", "SE", "n_cells", "clusters"]
    ].rename(
        columns={
            "specification": "Specification",
            "measure": "Outcome",
            "term": "Term",
            "n_cells": "Cells",
            "clusters": "Clusters",
        }
    )
    slash = chr(92)
    lines = [
        slash + "begin{table}[htbp]",
        slash + "centering",
        slash + "caption{Normal-goods census DiD estimates (percentage points)}",
        slash + "label{tab:normal-goods}",
        slash + "resizebox{" + slash + "linewidth}{!}{%",
        slash + "begin{tabular}{lrrrrrr}",
        slash + "toprule",
        "Specification & Outcome & Term & Estimate & SE & Cells & Clusters " + slash * 2,
        slash + "midrule",
    ]
    for row in output.itertuples(index=False, name=None):
        cells = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(f"{value:.3f}" if np.isfinite(value) else "")
            else:
                cells.append(latex_escape(value))
        lines.append(" & ".join(cells) + " " + slash * 2)
    lines.extend(
        [
            slash + "bottomrule",
            slash + "end{tabular}%",
            "}",
            slash + "end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def build_full_latex_table(education: pd.DataFrame, dwelling: pd.DataFrame) -> str:
    order = [label for label, _ in TARGET_GROUPS.values()] + ["Honduras"]
    panel_a_rows = []
    for group in order:
        frame = education.loc[education["group"].eq(group)].set_index("year")
        coverage_value = frame["treatment_coverage"].iloc[0]
        coverage = "" if pd.isna(coverage_value) else str(coverage_value)
        cells = [
            latex_escape(group),
            coverage,
            *[f"{frame.loc[year, 'population'] / 1_000:,.1f}" for year in YEARS],
            *[f"{frame.loc[year, 'mean_years_schooling_age25plus']:.1f}" for year in YEARS],
            *[
                f"{100 * frame.loc[year, 'share_self_employed_classwk_age15plus']:.1f} / "
                f"{100 * frame.loc[year, 'share_wage_salary_classwk_age15plus']:.1f}"
                for year in YEARS
            ],
        ]
        panel_a_rows.append(" & ".join(cells) + r" \\")

    dwelling_lookup = dwelling.loc[
        dwelling["unit"].isin(["Clean 50-kt IPUMS groups", "Honduras"])
    ].set_index(["unit", "year"])
    panel_b_rows = []
    for column, label in DWELLING_MEASURES:
        cells = [label]
        for year in YEARS:
            cells.extend(
                [
                    f"{100 * dwelling_lookup.loc[('Clean 50-kt IPUMS groups', year), column]:.1f}",
                    f"{100 * dwelling_lookup.loc[('Honduras', year), column]:.1f}",
                ]
            )
        panel_b_rows.append(" & ".join(cells) + r" \\")

    return "\n".join(
        [
            r"\textbf{Panel A. Population, adult education, and class of worker in census years}",
            r"\par\smallskip",
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{lcrrrrrrrrrr}",
            r"\toprule",
            r" & & \multicolumn{3}{c}{Population (thousands)} & \multicolumn{3}{c}{Mean school years, age 25+} & \multicolumn{3}{c}{CLASSWK: self-employed / wage-salary (\%), age 15+} \\",
            r"\cmidrule(lr){3-5}\cmidrule(lr){6-8}\cmidrule(lr){9-11}",
            r"IPUMS geography & 50-kt coverage & 1988 & 2001 & 2013 & 1988 & 2001 & 2013 & 1988 & 2001 & 2013 \\",
            r"\midrule",
            *panel_a_rows,
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\par\medskip",
            r"\textbf{Panel B. Household-weighted dwelling characteristics}",
            r"\par\smallskip",
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{lrrrrrr}",
            r"\toprule",
            r" & \multicolumn{2}{c}{1988} & \multicolumn{2}{c}{2001} & \multicolumn{2}{c}{2013} \\",
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
            r"Characteristic (\% of households) & Treated & Honduras & Treated & Honduras & Treated & Honduras \\",
            r"\midrule",
            *panel_b_rows,
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            "",
        ]
    )


def build_latex_table(education: pd.DataFrame, dwelling: pd.DataFrame) -> str:
    order = [
        "Colon group: Balfate--Iriona",
        "Colon group: Saba--Tocoa",
        "Bay Islands group",
        "Olancho group: Gualaco--San Esteban",
        "Honduras",
        "Gracias a Dios group",
    ]
    panel_a_rows = []
    for group in order:
        frame = education.loc[education["group"].eq(group)].set_index("year")
        coverage_value = frame["treatment_coverage"].iloc[0]
        coverage = "" if pd.isna(coverage_value) else str(coverage_value)
        label = "Gracias a Dios group*" if group == "Gracias a Dios group" else group
        cells = [
            latex_escape(label),
            coverage,
            *[f"{frame.loc[year, 'population'] / 1_000:,.1f}" for year in YEARS],
            *[f"{frame.loc[year, 'mean_years_schooling_age25plus']:.1f}" for year in YEARS],
        ]
        panel_a_rows.append(" & ".join(cells) + r" \\")

    dwelling_lookup = dwelling.loc[
        dwelling["unit"].isin(["Clean 50-kt IPUMS groups", "Honduras"])
    ].set_index(["unit", "year"])
    measures = [
        ("share_electricity", "Electricity"),
        ("share_sewage_or_septic", "Sewer or septic"),
        ("share_masonry_wall", "Masonry wall"),
        ("share_sheet_metal_roof", "Sheet-metal roof"),
        ("share_refrigerator", "Refrigerator"),
        ("share_television", "Television"),
    ]
    panel_b_rows = []
    for column, label in measures:
        cells = [label, r"--", r"--", r"--"]
        for year in YEARS:
            treated = 100 * dwelling_lookup.loc[("Clean 50-kt IPUMS groups", year), column]
            honduras = 100 * dwelling_lookup.loc[("Honduras", year), column]
            cells.extend([f"{treated:.1f}", f"{honduras:.1f}", f"{treated - honduras:+.1f}"])
        panel_b_rows.append(" & ".join(cells) + r" \\")

    return "\n".join(
        [
            r"\textbf{Panel A. Population and adult education in census years}",
            r"\par\smallskip",
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{lcrrrrrr}",
            r"\toprule",
            r" & & \multicolumn{3}{c}{Population (thousands)} & \multicolumn{3}{c}{Mean school years, age 25+} \\",
            r"\cmidrule(lr){3-5}\cmidrule(lr){6-8}",
            r"IPUMS geography & 50-kt coverage & 1988 & 2001 & 2013 & 1988 & 2001 & 2013 \\",
            r"\midrule",
            *panel_a_rows,
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\par\medskip",
            r"\textbf{Panel B. Household-weighted dwelling characteristics}",
            r"\par\smallskip",
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{lrrrrrrrrrrrr}",
            r"\toprule",
            r" & \multicolumn{3}{c}{1974} & \multicolumn{3}{c}{1988} & \multicolumn{3}{c}{2001} & \multicolumn{3}{c}{2013} \\",
            r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}\cmidrule(lr){11-13}",
            r"Characteristic (\% of households) & Treated & Honduras & Diff. & Treated & Honduras & Diff. & Treated & Honduras & Diff. & Treated & Honduras & Diff. \\",
            r"\midrule",
            *panel_b_rows,
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            "",
        ]
    )


def write_text(text: str, paths: list[Path]) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main() -> None:
    for path in [HOUSEHOLDS, EDUCATION, DWELLING]:
        if not path.exists():
            raise FileNotFoundError(f"Missing packaged census input: {path.relative_to(ROOT)}")

    households = pd.read_csv(HOUSEHOLDS)
    education = pd.read_csv(EDUCATION)
    dwelling = pd.read_csv(DWELLING)
    results = build_normal_goods_results(households)

    main_table = build_latex_table(education, dwelling)
    full_table = build_full_latex_table(education, dwelling)
    estimate_table = normal_goods_table(results)

    write_text(
        main_table,
        [
            PAPER / "main_results" / "tables" / "dwelling" / "honduras_50kt_population_education_dwelling.tex",
            OUT / "tables" / "dwelling" / "honduras_50kt_population_education_dwelling.tex",
        ],
    )
    write_text(
        full_table,
        [
            PAPER / "appendix" / "census" / "honduras_50kt_population_education_dwelling_full.tex",
            OUT / "tables" / "structured" / "appendix" / "census" / "honduras_50kt_population_education_dwelling_full.tex",
        ],
    )
    write_text(
        estimate_table,
        [
            PAPER / "appendix" / "census" / "normal_goods_estimates.tex",
            OUT / "tables" / "structured" / "appendix" / "census" / "normal_goods_estimates.tex",
        ],
    )

    figure_paths = [
        PAPER / "appendix" / "census" / "normal_goods_did_event_studies.png",
        OUT / "figures" / "structured" / "appendix" / "census" / "normal_goods_did_event_studies.png",
    ]
    for path in figure_paths:
        save_normal_goods_figure(results, path)

    result_path = OUT / "tables" / "structured" / "appendix" / "census" / "normal_goods_estimates.csv"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(result_path, index=False)
    print("Built final Honduran census tables, figure, and normal-goods estimates")


if __name__ == "__main__":
    main()
