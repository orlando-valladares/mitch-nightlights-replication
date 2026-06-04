from __future__ import annotations

import gzip
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PACKAGED_INPUTS = [
    ROOT / "working" / "data" / "processed" / "municipalities_adm2_analytical.geojson",
    ROOT
    / "working"
    / "data"
    / "processed"
    / "did_dashboard"
    / "gaul_name_matched_municipalities_analytical.geojson",
]


def restore_if_needed(path: Path) -> None:
    if path.exists():
        return
    gz_path = path.with_suffix(path.suffix + ".gz")
    if not gz_path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz_path, "rb") as src, path.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    print(f"Restored {path.relative_to(ROOT)} from {gz_path.name}")


def main() -> None:
    for path in PACKAGED_INPUTS:
        restore_if_needed(path)


if __name__ == "__main__":
    main()
