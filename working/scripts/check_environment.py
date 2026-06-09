from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_MODULES = [
    "affine",
    "geopandas",
    "matplotlib",
    "numpy",
    "openpyxl",
    "pandas",
    "PIL",
    "pyproj",
    "rasterio",
    "scipy",
    "shapely",
]
REQUIRED_INPUTS = [
    ROOT / "raw" / "dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv",
    ROOT / "raw" / "chirps_mitch_daily_stack_19981027_19981104_ca5.tif",
    ROOT / "raw" / "chirps_climatology_stack_1981_present_oct27_nov04_ca5.tif",
    ROOT / "raw" / "external" / "ebtrk_atlc_1851_2021.txt",
    ROOT / "working" / "data" / "processed" / "municipalities_adm2_analytical.geojson.gz",
    ROOT / "working" / "data" / "processed" / "did_dashboard" / "gaul_name_matched_municipalities_analytical.geojson.gz",
    ROOT / "working" / "data" / "replication_inputs" / "ipums_honduras" / "households.csv",
    ROOT / "working" / "data" / "replication_inputs" / "ipums_honduras" / "honduras_50kt_population_education.csv",
    ROOT / "working" / "data" / "replication_inputs" / "ipums_honduras" / "honduras_50kt_dwelling_summary.csv",
    ROOT / "paper" / "main.tex",
    ROOT / "paper" / "sample.bib",
]


def main() -> None:
    missing_modules = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    missing_inputs = [path.relative_to(ROOT) for path in REQUIRED_INPUTS if not path.exists()]
    if missing_modules or missing_inputs:
        if missing_modules:
            print("Missing Python modules:", ", ".join(missing_modules), file=sys.stderr)
            print(
                "Install them with: python -m pip install -r working/scripts/requirements.txt",
                file=sys.stderr,
            )
        if missing_inputs:
            print("Missing packaged inputs:", file=sys.stderr)
            for path in missing_inputs:
                print(f"  - {path}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Environment check passed with {sys.executable}")


if __name__ == "__main__":
    main()
