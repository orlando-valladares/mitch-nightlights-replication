from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RAW_DATA = ROOT / "raw" / "dwelling" / "ipumsi_00003.dat"
ATTRIBUTES = ROOT / "working" / "data" / "processed" / "municipality_attributes.csv"
OUTPUT = ROOT / "working" / "data" / "replication_inputs" / "ipums_honduras"
WORKING_OUT = OUTPUT
TABLE_OUT = OUTPUT
FIGURE_OUT = ROOT / "working" / "figures" / "ipums_source_prep"

YEARS = [1988, 2001, 2013]
TREATMENT_COLUMN = "ebtrk_treat50_r50_all"

# IPUMS fixed-width positions are zero-based, half-open here.
COLSPECS = {
    "year": (3, 7),
    "sample": (7, 16),
    "serial": (16, 28),
    "hhwt_raw": (28, 36),
    "popdensgeo2": (61, 73),
    "areamollwgeo2": (83, 93),
    "geo1_hn": (93, 99),
    "geo2_hn": (99, 108),
    "ownership": (108, 109),
    "electric": (112, 113),
    "watsup": (113, 115),
    "sewage": (115, 117),
    "fuelcook": (117, 119),
    "refrig": (123, 124),
    "tv": (124, 126),
    "rooms": (127, 129),
    "bedrooms": (129, 131),
    "toilet": (133, 135),
    "floor": (136, 139),
    "wall": (139, 142),
    "roof": (142, 144),
    "hhtype": (145, 147),
    "pernum": (153, 157),
    "perwt_raw": (157, 165),
}

IPUMS_GROUPS = {
    340002001: {
        "department": "Colon",
        "label": "Balfate, Bonito Oriental, Limon, Santa Fe, Santa Rosa de Aguan, Trujillo, Iriona",
        "municipalities": [
            "Balfate",
            "Bonito Oriental",
            "Limon",
            "Santa Fe",
            "Santa Rosa De Aguan",
            "Trujillo",
            "Iriona",
        ],
    },
    340002003: {
        "department": "Colon",
        "label": "Saba, Sonaguera, Tocoa",
        "municipalities": ["Saba", "Sonaguera", "Tocoa"],
    },
    340009001: {
        "department": "Gracias A Dios",
        "label": "Ahuas, Brus Laguna, Juan Francisco Bulnes, Puerto Lempira, Villeda Morales, Wampusirpi",
        "municipalities": [
            "Ahuas",
            "Brus Laguna",
            "Juan Francisco Bulnes",
            "Puerto Lempira",
            "Villeda Morales",
            "Wampusirpi",
        ],
    },
    340011001: {
        "department": "Islas De Bahia",
        "label": "Guanaja, Jose Santos Guardiola, Roatan, Utila",
        "municipalities": ["Guanaja", "Jose Santos Guardiola", "Roatan", "Utila"],
    },
    340015006: {
        "department": "Olancho",
        "label": "Gualaco, San Esteban",
        "municipalities": ["Gualaco", "San Esteban"],
    },
}

TREATED_TO_IPUMS = {
    "Balfate": 340002001,
    "Bonito Oriental": 340002001,
    "Iriona": 340002001,
    "Limon": 340002001,
    "Santa Fe": 340002001,
    "Santa Rosa De Aguan": 340002001,
    "Trujillo": 340002001,
    "Saba": 340002003,
    "Sonaguera": 340002003,
    "Tocoa": 340002003,
    "Brus Laguna": 340009001,
    "Guanaja": 340011001,
    "Jose Santos Guardiola": 340011001,
    "Roatan": 340011001,
    "Gualaco": 340015006,
    "San Esteban": 340015006,
}

CLEAN_GROUP_CODES = {340002001, 340002003, 340015006}
ALL_TARGET_GROUP_CODES = set(IPUMS_GROUPS)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Za-z0-9]+", " ", text).strip().casefold()


def weighted_share(frame: pd.DataFrame, indicator: pd.Series, valid: pd.Series) -> float:
    use = valid.fillna(False) & frame["hhwt"].gt(0)
    if not use.any():
        return float("nan")
    return float((indicator.fillna(False)[use] * frame.loc[use, "hhwt"]).sum() / frame.loc[use, "hhwt"].sum())


def weighted_mean(frame: pd.DataFrame, value: pd.Series, valid: pd.Series) -> float:
    use = valid.fillna(False) & frame["hhwt"].gt(0)
    if not use.any():
        return float("nan")
    return float((value[use] * frame.loc[use, "hhwt"]).sum() / frame.loc[use, "hhwt"].sum())


def make_crosswalk() -> pd.DataFrame:
    attributes = pd.read_csv(ATTRIBUTES)
    treated = attributes.loc[
        attributes["country_name"].eq("Honduras") & attributes[TREATMENT_COLUMN].eq(1),
        ["muni_key", "department_name", "municipality_name", "ebtrk_share_r50_all", "ebtrk_share_r64_all"],
    ].copy()
    mapping = {normalize_name(name): code for name, code in TREATED_TO_IPUMS.items()}
    treated["geo2_hn"] = treated["municipality_name"].map(lambda value: mapping.get(normalize_name(value)))
    if treated["geo2_hn"].isna().any():
        missing = treated.loc[treated["geo2_hn"].isna(), "municipality_name"].tolist()
        raise ValueError(f"Unmatched treated municipalities: {missing}")
    treated["geo2_hn"] = treated["geo2_hn"].astype(int)
    treated_counts = treated.groupby("geo2_hn")["municipality_name"].nunique()
    treated["ipums_group_label"] = treated["geo2_hn"].map(lambda code: IPUMS_GROUPS[code]["label"])
    treated["ipums_group_municipality_count"] = treated["geo2_hn"].map(
        lambda code: len(IPUMS_GROUPS[code]["municipalities"])
    )
    treated["treated_municipalities_in_group"] = treated["geo2_hn"].map(treated_counts)
    treated["clean_treated_group"] = (
        treated["treated_municipalities_in_group"].eq(treated["ipums_group_municipality_count"])
    )
    treated["geography_note"] = treated["clean_treated_group"].map(
        {
            True: "All municipalities in this harmonized IPUMS group satisfy the 50-kt treatment rule.",
            False: "This harmonized IPUMS group combines treated and untreated municipalities.",
        }
    )
    return treated.sort_values(["geo2_hn", "municipality_name"]).reset_index(drop=True)


def read_ipums() -> tuple[pd.DataFrame, pd.DataFrame]:
    colspecs = list(COLSPECS.values())
    names = list(COLSPECS)
    household_chunks: list[pd.DataFrame] = []
    household_size_chunks: list[pd.DataFrame] = []
    population_chunks: list[pd.DataFrame] = []

    for chunk in pd.read_fwf(RAW_DATA, colspecs=colspecs, names=names, chunksize=200_000):
        chunk = chunk.loc[chunk["year"].isin(YEARS)].copy()
        if chunk.empty:
            continue
        chunk["hhwt"] = chunk["hhwt_raw"] / 100
        chunk["perwt"] = chunk["perwt_raw"] / 100

        population_chunks.append(
            chunk.groupby(["year", "geo2_hn"], as_index=False)["perwt"].sum().rename(columns={"perwt": "population"})
        )

        private_persons = chunk.loc[chunk["hhtype"].ne(11), ["year", "serial", "geo2_hn"]]
        household_size_chunks.append(
            private_persons.groupby(["year", "serial", "geo2_hn"], as_index=False)
            .size()
            .rename(columns={"size": "household_size"})
        )

        household_chunks.append(chunk.loc[chunk["pernum"].eq(1) & chunk["hhtype"].ne(11)].copy())

    households = pd.concat(household_chunks, ignore_index=True)
    household_sizes = (
        pd.concat(household_size_chunks, ignore_index=True)
        .groupby(["year", "serial", "geo2_hn"], as_index=False)["household_size"]
        .sum()
    )
    households = households.merge(
        household_sizes,
        on=["year", "serial", "geo2_hn"],
        how="left",
        validate="one_to_one",
    )
    population = (
        pd.concat(population_chunks, ignore_index=True)
        .groupby(["year", "geo2_hn"], as_index=False)["population"]
        .sum()
    )
    return households, population


def summarize_households(frame: pd.DataFrame, population: float, unit: str, unit_type: str) -> dict[str, float | str]:
    valid_ownership = frame["ownership"].isin([1, 2])
    valid_electric = frame["electric"].isin([1, 2])
    valid_water = frame["watsup"].between(10, 20)
    valid_sewage = frame["sewage"].between(10, 20)
    valid_fuel = frame["fuelcook"].ne(0) & frame["fuelcook"].ne(99)
    valid_refrig = frame["refrig"].isin([1, 2])
    valid_tv = frame["tv"].isin([10, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 40, 41, 42, 43])
    valid_toilet = frame["toilet"].ne(0) & frame["toilet"].ne(99)
    valid_floor = frame["floor"].ne(0) & frame["floor"].ne(999)
    valid_wall = frame["wall"].ne(0) & frame["wall"].ne(999)
    valid_roof = frame["roof"].ne(0) & frame["roof"].ne(99)
    valid_rooms = frame["rooms"].between(1, 30)
    valid_bedrooms = frame["bedrooms"].between(0, 20)

    persons_per_room = frame["household_size"] / frame["rooms"]
    persons_per_bedroom = frame["household_size"] / frame["bedrooms"].replace(0, pd.NA)
    return {
        "unit": unit,
        "unit_type": unit_type,
        "year": int(frame["year"].iloc[0]),
        "population": population,
        "households": frame["hhwt"].sum(),
        "sample_households": int(len(frame)),
        "mean_household_size": weighted_mean(frame, frame["household_size"], frame["household_size"].gt(0)),
        "share_owned": weighted_share(frame, frame["ownership"].eq(1), valid_ownership),
        "share_electricity": weighted_share(frame, frame["electric"].eq(1), valid_electric),
        "share_piped_water": weighted_share(frame, frame["watsup"].between(10, 19), valid_water),
        "share_sewage_or_septic": weighted_share(frame, frame["sewage"].between(10, 19), valid_sewage),
        "share_wood_solid_fuel": weighted_share(frame, frame["fuelcook"].between(50, 59), valid_fuel),
        "share_refrigerator": weighted_share(frame, frame["refrig"].eq(2), valid_refrig),
        "share_television": weighted_share(frame, frame["tv"].between(20, 43), valid_tv),
        "share_no_toilet": weighted_share(frame, frame["toilet"].eq(10), valid_toilet),
        "share_flush_toilet": weighted_share(frame, frame["toilet"].eq(21), valid_toilet),
        "share_earth_floor": weighted_share(frame, frame["floor"].eq(100), valid_floor),
        "share_finished_floor": weighted_share(frame, frame["floor"].between(200, 299), valid_floor),
        "share_masonry_wall": weighted_share(
            frame,
            frame["wall"].between(500, 526) | frame["wall"].between(544, 548),
            valid_wall,
        ),
        "share_adobe_mud_wall": weighted_share(frame, frame["wall"].between(527, 543), valid_wall),
        "share_wood_wall": weighted_share(frame, frame["wall"].between(300, 399), valid_wall),
        "share_concrete_tile_roof": weighted_share(frame, frame["roof"].between(10, 20), valid_roof),
        "share_sheet_metal_roof": weighted_share(frame, frame["roof"].between(33, 38), valid_roof),
        "share_wood_thatch_scrap_roof": weighted_share(
            frame,
            frame["roof"].between(40, 79) | frame["roof"].eq(90),
            valid_roof,
        ),
        "mean_rooms": weighted_mean(frame, frame["rooms"], valid_rooms),
        "mean_bedrooms": weighted_mean(frame, frame["bedrooms"], valid_bedrooms),
        "share_more_than_3_per_room": weighted_share(frame, persons_per_room.gt(3), valid_rooms),
        "share_more_than_3_per_bedroom": weighted_share(
            frame,
            persons_per_bedroom.gt(3),
            valid_bedrooms & frame["bedrooms"].gt(0),
        ),
    }


def build_summary(households: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    population_lookup = population.set_index(["year", "geo2_hn"])["population"]
    rows: list[dict[str, float | str]] = []
    for year in YEARS:
        year_households = households.loc[households["year"].eq(year)]
        for code, metadata in IPUMS_GROUPS.items():
            frame = year_households.loc[year_households["geo2_hn"].eq(code)]
            pop = float(population_lookup.get((year, code), 0))
            rows.append(summarize_households(frame, pop, metadata["label"], "IPUMS harmonized group"))

        for codes, label, unit_type in [
            (CLEAN_GROUP_CODES, "Clean 50-kt IPUMS groups", "Aggregate"),
            (ALL_TARGET_GROUP_CODES, "All IPUMS groups containing 50-kt municipalities", "Aggregate"),
        ]:
            frame = year_households.loc[year_households["geo2_hn"].isin(codes)]
            pop = float(population.loc[population["year"].eq(year) & population["geo2_hn"].isin(codes), "population"].sum())
            rows.append(summarize_households(frame, pop, label, unit_type))

        national_population = float(population.loc[population["year"].eq(year), "population"].sum())
        rows.append(summarize_households(year_households, national_population, "Honduras", "National"))
    return pd.DataFrame(rows)


def make_figures(summary: pd.DataFrame) -> None:
    FIGURE_OUT.mkdir(parents=True, exist_ok=True)
    groups = summary.loc[summary["unit_type"].eq("IPUMS harmonized group")].copy()
    short_labels = {
        IPUMS_GROUPS[340002001]["label"]: "Colon group (7/7 treated)",
        IPUMS_GROUPS[340002003]["label"]: "Colon group (3/3 treated)",
        IPUMS_GROUPS[340009001]["label"]: "Gracias a Dios (1/6 treated)",
        IPUMS_GROUPS[340011001]["label"]: "Bay Islands (3/4 treated)",
        IPUMS_GROUPS[340015006]["label"]: "Olancho group (2/2 treated)",
    }
    fig, ax = plt.subplots(figsize=(10, 6))
    for unit, frame in groups.groupby("unit", sort=False):
        ax.plot(frame["year"], frame["population"] / 1_000, marker="o", linewidth=2, label=short_labels[unit])
    ax.set_title("Population in IPUMS groups containing 50-kt municipalities")
    ax.set_xlabel("Census year")
    ax.set_ylabel("Population (thousands)")
    ax.set_xticks(YEARS)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_OUT / "honduras_50kt_population_by_ipums_group.png", dpi=220)
    plt.close(fig)

    plot_data = summary.loc[
        summary["unit"].isin(["Clean 50-kt IPUMS groups", "Honduras"])
    ].copy()
    measures = [
        ("share_electricity", "Electricity"),
        ("share_sewage_or_septic", "Sewer or septic"),
        ("share_wood_solid_fuel", "Wood/solid cooking fuel"),
        ("share_earth_floor", "Earth floor"),
        ("share_masonry_wall", "Masonry wall"),
        ("share_sheet_metal_roof", "Sheet-metal roof"),
    ]
    colors = {"Clean 50-kt IPUMS groups": "#9f1d20", "Honduras": "#4d4d4d"}
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True, sharey=True)
    for ax, (column, title) in zip(axes.flat, measures):
        for unit, frame in plot_data.groupby("unit", sort=False):
            ax.plot(
                frame["year"],
                100 * frame[column],
                marker="o",
                linewidth=2,
                color=colors[unit],
                linestyle="-" if unit.startswith("Clean") else "--",
                label=unit,
            )
        ax.set_title(title)
        ax.set_xticks(YEARS)
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.2)
    axes[0, 0].set_ylabel("Percent of households")
    axes[1, 0].set_ylabel("Percent of households")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.suptitle("Dwelling conditions in cleanly identified 50-kt census groups", y=0.99)
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    fig.savefig(FIGURE_OUT / "honduras_50kt_dwelling_services_trends.png", dpi=220)
    plt.close(fig)

    latest = groups.loc[groups["year"].eq(2013)].copy()
    heatmap_measures = [
        ("share_electricity", "Electricity"),
        ("share_sewage_or_septic", "Sewer/septic"),
        ("share_wood_solid_fuel", "Solid fuel"),
        ("share_earth_floor", "Earth floor"),
        ("share_masonry_wall", "Masonry wall"),
        ("share_sheet_metal_roof", "Sheet-metal roof"),
    ]
    latest["short_label"] = latest["unit"].map(short_labels)
    values = 100 * latest[[column for column, _ in heatmap_measures]].to_numpy()
    fig, ax = plt.subplots(figsize=(11, 5))
    image = ax.imshow(values, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(heatmap_measures)), [label for _, label in heatmap_measures])
    ax.set_yticks(range(len(latest)), latest["short_label"])
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            ax.text(column, row, f"{values[row, column]:.0f}", ha="center", va="center", fontsize=9)
    ax.set_title("Dwelling conditions in IPUMS groups containing 50-kt municipalities, 2013 (%)")
    colorbar = fig.colorbar(image, ax=ax, pad=0.02)
    colorbar.set_label("Percent of households")
    fig.tight_layout()
    fig.savefig(FIGURE_OUT / "honduras_50kt_dwelling_2013_heatmap.png", dpi=220)
    plt.close(fig)



HOUSEHOLD_MEASURES = {
    "electricity": (lambda d: d["electric"].eq(1), lambda d: d["electric"].isin([1, 2])),
    "piped_water": (lambda d: d["watsup"].between(10, 19), lambda d: d["watsup"].between(10, 20)),
    "sewer_or_septic": (lambda d: d["sewage"].between(10, 19), lambda d: d["sewage"].between(10, 20)),
    "refrigerator": (lambda d: d["refrig"].eq(2), lambda d: d["refrig"].isin([1, 2])),
    "television": (lambda d: d["tv"].between(20, 43), lambda d: d["tv"].between(10, 43)),
    "earth_floor": (lambda d: d["floor"].eq(100), lambda d: d["floor"].ne(0) & d["floor"].ne(999)),
    "masonry_wall": (
        lambda d: d["wall"].between(500, 526) | d["wall"].between(544, 548),
        lambda d: d["wall"].ne(0) & d["wall"].ne(999),
    ),
    "sheet_metal_roof": (lambda d: d["roof"].between(33, 38), lambda d: d["roof"].ne(0) & d["roof"].ne(99)),
    "solid_cooking_fuel": (lambda d: d["fuelcook"].between(50, 59), lambda d: d["fuelcook"].ne(0) & d["fuelcook"].ne(99)),
}


def build_household_cells(households: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for measure, (indicator_fn, valid_fn) in HOUSEHOLD_MEASURES.items():
        valid = valid_fn(households) & households["hhwt"].gt(0)
        use = households.loc[valid, ["year", "geo2_hn", "hhwt"]].copy()
        use["measure"] = measure
        use["numerator"] = indicator_fn(households).loc[valid].astype(float).to_numpy() * use["hhwt"].to_numpy()
        use["sample_n"] = 1
        rows.append(
            use.groupby(["year", "geo2_hn", "measure"], as_index=False).agg(
                weight=("hhwt", "sum"),
                numerator=("numerator", "sum"),
                sample_n=("sample_n", "sum"),
            )
        )
    result = pd.concat(rows, ignore_index=True)
    result["share"] = result["numerator"] / result["weight"]
    return result.sort_values(["year", "geo2_hn", "measure"]).reset_index(drop=True)


EDUCATION_COLSPECS = [
    (3, 7),
    (99, 108),
    (157, 165),
    (203, 206),
    (252, 253),
    (256, 258),
    (266, 267),
]
EDUCATION_NAMES = ["year", "geo2_hn", "perwt_raw", "age", "edattain", "yrschool", "classwk"]
EDUCATION_TARGET_GROUPS = {
    340002001: ("Colon group: Balfate--Iriona", "7/7"),
    340002003: ("Colon group: Saba--Tocoa", "3/3"),
    340009001: ("Gracias a Dios group", "1/6"),
    340011001: ("Bay Islands group", "3/4"),
    340015006: ("Olancho group: Gualaco--San Esteban", "2/2"),
}


def read_population_education() -> pd.DataFrame:
    chunks = []
    for chunk in pd.read_fwf(
        RAW_DATA,
        colspecs=EDUCATION_COLSPECS,
        names=EDUCATION_NAMES,
        chunksize=250_000,
    ):
        chunk = chunk.loc[chunk["year"].isin(YEARS)].copy()
        if chunk.empty:
            continue
        chunk["perwt"] = chunk["perwt_raw"] / 100
        adult = chunk["age"].ge(25)
        valid_school = adult & chunk["yrschool"].between(0, 18)
        valid_attainment = adult & chunk["edattain"].isin([1, 2, 3, 4])
        valid_classwk = chunk["age"].ge(15) & chunk["classwk"].isin([1, 2, 3, 4])
        chunk["population_weight"] = chunk["perwt"]
        chunk["school_weight"] = chunk["perwt"].where(valid_school, 0)
        chunk["school_years_weighted"] = (chunk["yrschool"] * chunk["perwt"]).where(valid_school, 0)
        chunk["attainment_weight"] = chunk["perwt"].where(valid_attainment, 0)
        chunk["secondary_weight"] = (chunk["edattain"].isin([3, 4]).astype(float) * chunk["perwt"]).where(valid_attainment, 0)
        chunk["classwk_weight"] = chunk["perwt"].where(valid_classwk, 0)
        chunk["self_employed_weight"] = (chunk["classwk"].eq(1).astype(float) * chunk["perwt"]).where(valid_classwk, 0)
        chunk["wage_salary_weight"] = (chunk["classwk"].eq(2).astype(float) * chunk["perwt"]).where(valid_classwk, 0)
        chunks.append(
            chunk.groupby(["year", "geo2_hn"], as_index=False)[
                [
                    "population_weight",
                    "school_weight",
                    "school_years_weighted",
                    "attainment_weight",
                    "secondary_weight",
                    "classwk_weight",
                    "self_employed_weight",
                    "wage_salary_weight",
                ]
            ].sum()
        )
    by_geo = pd.concat(chunks, ignore_index=True).groupby(["year", "geo2_hn"], as_index=False).sum(numeric_only=True)
    rows = []
    for year in YEARS:
        year_data = by_geo.loc[by_geo["year"].eq(year)]
        for code, (label, coverage) in EDUCATION_TARGET_GROUPS.items():
            values = year_data.loc[year_data["geo2_hn"].eq(code)].iloc[0]
            rows.append(
                {
                    "group": label,
                    "treatment_coverage": coverage,
                    "year": year,
                    "population": values["population_weight"],
                    "mean_years_schooling_age25plus": values["school_years_weighted"] / values["school_weight"],
                    "share_secondary_plus_age25plus": values["secondary_weight"] / values["attainment_weight"],
                    "share_self_employed_classwk_age15plus": values["self_employed_weight"] / values["classwk_weight"],
                    "share_wage_salary_classwk_age15plus": values["wage_salary_weight"] / values["classwk_weight"],
                }
            )
        values = year_data.sum(numeric_only=True)
        rows.append(
            {
                "group": "Honduras",
                "treatment_coverage": "",
                "year": year,
                "population": values["population_weight"],
                "mean_years_schooling_age25plus": values["school_years_weighted"] / values["school_weight"],
                "share_secondary_plus_age25plus": values["secondary_weight"] / values["attainment_weight"],
                "share_self_employed_classwk_age15plus": values["self_employed_weight"] / values["classwk_weight"],
                "share_wage_salary_classwk_age15plus": values["wage_salary_weight"] / values["classwk_weight"],
            }
        )
    return pd.DataFrame(rows)

def main() -> None:
    WORKING_OUT.mkdir(parents=True, exist_ok=True)
    if not RAW_DATA.exists():
        raise FileNotFoundError(
            "Place the licensed IPUMS fixed-width extract at raw/dwelling/ipumsi_00003.dat. "
            "The raw extract is intentionally excluded from the public repository."
        )

    crosswalk = make_crosswalk()
    households, population = read_ipums()
    summary = build_summary(households, population)
    household_cells = build_household_cells(households)
    education = read_population_education()

    crosswalk.to_csv(WORKING_OUT / "honduras_50kt_ipums_geography_crosswalk.csv", index=False)
    summary.to_csv(WORKING_OUT / "honduras_50kt_dwelling_summary.csv", index=False)
    household_cells.to_csv(WORKING_OUT / "households.csv", index=False)
    education.to_csv(WORKING_OUT / "honduras_50kt_population_education.csv", index=False)

    print(f"Treated municipalities: {len(crosswalk)}")
    print(f"Harmonized IPUMS groups: {crosswalk.geo2_hn.nunique()}")
    print(f"Household aggregate cells: {len(household_cells)}")
    print("Rebuilt disclosure-safe IPUMS replication inputs in", WORKING_OUT)


if __name__ == "__main__":
    main()
