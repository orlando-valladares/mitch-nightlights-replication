from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKING_DIR = ROOT / "working"
RAW_DIR = ROOT / "raw"
DATA_DIR = WORKING_DIR / "data"
EXTERNAL_DIR = RAW_DIR / "external"
PROCESSED_DIR = DATA_DIR / "processed"
WEB_DIR = DATA_DIR / "web"
DASHBOARD_DIR = WORKING_DIR / "dashboard"

IBTRACS_NA_CSV_URL = (
    "https://www.ncei.noaa.gov/data/"
    "international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/ibtracs.NA.list.v04r01.csv"
)
IBTRACS_SHAPEFILE_DIR_URL = (
    "https://www.ncei.noaa.gov/data/"
    "international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/shapefile/"
)
EBTRK_PAGE_URL = (
    "https://rammb2.cira.colostate.edu/research/tropical-cyclones/"
    "tc_extended_best_track_dataset/"
)
EBTRK_README_URL = (
    "https://rammb2.cira.colostate.edu/wp-content/uploads/2020/11/"
    "EBTRK_README_v3.0.2_16-Oct-2022.txt"
)
NHC_MITCH_TCR_URL = "https://www.nhc.noaa.gov/data/tcr/AL131998_Mitch.pdf"

DEFAULT_NTL_CSV = RAW_DIR / "dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv"
DEFAULT_IBTRACS_CSV = EXTERNAL_DIR / "ibtracs.NA.list.v04r01.csv"
DEFAULT_EBTRK_TXT = EXTERNAL_DIR / "ebtrk_atlc_1851_2021.txt"

CENTRAL_AMERICA_ISO3 = ["BLZ", "GTM", "SLV", "HND", "NIC", "CRI", "PAN"]


def ensure_project_dirs() -> None:
    for path in [DATA_DIR, EXTERNAL_DIR, PROCESSED_DIR, WEB_DIR, DASHBOARD_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def resolve_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT / path


def assert_not_in_raw(path: str | Path) -> Path:
    """Guardrail: no pipeline output may be written under raw/."""
    resolved = resolve_path(path).resolve()
    raw_resolved = RAW_DIR.resolve()
    if resolved == raw_resolved or raw_resolved in resolved.parents:
        raise ValueError(f"Refusing to write inside raw/: {resolved}")
    return resolved


def output_path(path: str | Path) -> Path:
    resolved = assert_not_in_raw(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def raw_input_path(path: str | Path) -> Path:
    resolved = resolve_path(path)
    if resolved is None:
        raise ValueError("raw_input_path requires a path.")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def existing_input_path(path: str | Path | None) -> Path | None:
    resolved = resolve_path(path)
    if resolved and resolved.exists():
        return resolved
    return None
