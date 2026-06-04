from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from pipeline_config import (
    CENTRAL_AMERICA_ISO3,
    EBTRK_PAGE_URL,
    EBTRK_README_URL,
    EXTERNAL_DIR,
    IBTRACS_NA_CSV_URL,
    ensure_project_dirs,
    output_path,
    raw_input_path,
)
from pipeline_utils import write_json


USER_AGENT = "mitch-nightlights-pipeline/0.1 (research reproducibility)"


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            self._href = attrs_dict.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append({"href": self._href, "text": " ".join(self._text).strip()})
            self._href = None
            self._text = []


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download(url: str, destination: Path, overwrite: bool = False) -> dict[str, object]:
    destination = raw_input_path(destination)
    if destination.exists() and not overwrite:
        return {
            "url": url,
            "path": str(destination),
            "status": "exists",
            "bytes": destination.stat().st_size,
        }
    data = fetch_bytes(url)
    destination.write_bytes(data)
    return {
        "url": url,
        "path": str(destination),
        "status": "downloaded",
        "bytes": len(data),
    }


def parse_links(page_url: str) -> list[dict[str, str]]:
    html = fetch_bytes(page_url).decode("utf-8", errors="replace")
    parser = LinkCollector()
    parser.feed(html)
    links: list[dict[str, str]] = []
    for item in parser.links:
        href = item["href"]
        links.append({"text": item["text"], "url": urllib.parse.urljoin(page_url, href)})
    return links


def find_ebtrk_links() -> dict[str, str]:
    links = parse_links(EBTRK_PAGE_URL)
    atlantic = [link["url"] for link in links if "Atlantic Basin Dataset" in link["text"]]
    readmes = [link["url"] for link in links if "Documentation File" in link["text"]]
    if not atlantic:
        raise RuntimeError("Could not find an Atlantic Extended Best Track download link.")
    result = {"ebtrk_atlantic": atlantic[0]}
    if len(atlantic) > 1:
        result["ebtrk_atlantic_old_format"] = atlantic[1]
    result["ebtrk_readme"] = readmes[0] if readmes else EBTRK_README_URL
    return result


def download_geoboundaries_adm2(iso3: str, overwrite: bool = False) -> list[dict[str, object]]:
    api_url = f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM2/"
    metadata_path = raw_input_path(EXTERNAL_DIR / f"geoboundaries_adm2_{iso3}_metadata.json")
    if metadata_path.exists() and not overwrite:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata = json.loads(fetch_bytes(api_url).decode("utf-8"))
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    if isinstance(metadata, list):
        metadata = metadata[0]
    geojson_url = (
        metadata.get("gjDownloadURL")
        or metadata.get("simplifiedGeometryGeoJSON")
        or metadata.get("downloadURL")
    )
    if not geojson_url:
        raise RuntimeError(f"GeoBoundaries metadata for {iso3} did not include a GeoJSON URL.")
    geojson_path = EXTERNAL_DIR / f"geoboundaries_adm2_{iso3}.geojson"
    return [
        {
            "url": api_url,
            "path": str(metadata_path),
            "status": "metadata",
            "bytes": metadata_path.stat().st_size,
        },
        download(geojson_url, geojson_path, overwrite=overwrite),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download external public source data for the Mitch pipeline.")
    parser.add_argument("--overwrite", action="store_true", help="Redownload files that already exist.")
    parser.add_argument(
        "--skip-boundaries",
        action="store_true",
        help="Do not download GeoBoundaries ADM2 fallback boundaries.",
    )
    parser.add_argument(
        "--countries",
        nargs="+",
        default=CENTRAL_AMERICA_ISO3,
        help="ISO3 country codes for GeoBoundaries ADM2 downloads.",
    )
    args = parser.parse_args(argv)

    ensure_project_dirs()
    manifest: list[dict[str, object]] = []
    manifest.append(download(IBTRACS_NA_CSV_URL, EXTERNAL_DIR / "ibtracs.NA.list.v04r01.csv", args.overwrite))

    ebtrk_links = find_ebtrk_links()
    manifest.append(download(ebtrk_links["ebtrk_atlantic"], EXTERNAL_DIR / "ebtrk_atlc_1851_2021.txt", args.overwrite))
    if "ebtrk_atlantic_old_format" in ebtrk_links:
        manifest.append(
            download(
                ebtrk_links["ebtrk_atlantic_old_format"],
                EXTERNAL_DIR / "ebtrk_atlc_1851_2021_old_format.txt",
                args.overwrite,
            )
        )
    manifest.append(download(ebtrk_links["ebtrk_readme"], EXTERNAL_DIR / "EBTRK_README_v3.0.2.txt", args.overwrite))

    if not args.skip_boundaries:
        for iso3 in args.countries:
            try:
                manifest.extend(download_geoboundaries_adm2(iso3.upper(), overwrite=args.overwrite))
                time.sleep(0.2)
            except (urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
                manifest.append({"url": f"GeoBoundaries {iso3}", "path": None, "status": f"failed: {exc}"})

    manifest_path = raw_input_path(EXTERNAL_DIR / "download_manifest.json")
    write_json(manifest_path, manifest)
    print(f"Wrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
