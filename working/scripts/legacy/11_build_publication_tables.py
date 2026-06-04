from __future__ import annotations

import csv
import html
import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
PUB_TABLES = ROOT / "out" / "data" / "tables" / "publication"
OUT_DIR = ROOT / "out" / "data" / "tables" / "publication"
ODT_OUT = OUT_DIR / "economics_data_tables.odt"
TEX_OUT = OUT_DIR / "economics_data_tables_booktabs.tex"


COLUMNS = ["variable", "mean", "sd", "p10", "p25", "p50", "p75", "p90", "n", "source"]
HEADER_2 = ["", "Mean", "SD", "10", "25", "50", "75", "90", "N", "Source"]


LABELS = {
    "stable_sum": "Stable lights sum",
    "stable_count": "Valid stable-light pixels",
    "pre_mean_stable_sum": "Mean pre-1999 stable lights",
    "wind_kt": "Storm-center wind speed (kt)",
    "pressure_mb": "Storm-center pressure (mb)",
    "lat": "Storm-center latitude",
    "lon": "Storm-center longitude",
    "min_distance_to_track_km": "Minimum distance to track (km)",
    "centroid_min_distance_to_track_k": "Centroid distance to nearest track point (km)",
    "nearest_track_wind_kt": "Wind at nearest track point (kt)",
    "nearest_track_pressure_mb": "Pressure at nearest track point (mb)",
    "max_track_wind_within_50km": "Max track wind within 50 km (kt)",
    "max_track_wind_within_100km": "Max track wind within 100 km (kt)",
    "max_track_wind_within_150km": "Max track wind within 150 km (kt)",
    "max_track_wind_within_200km": "Max track wind within 200 km (kt)",
    "share_area_r34": "Share of area in R34 swath",
    "any_r34": "Any R34 swath overlap",
    "share_area_r50": "Share of area in R50 swath",
    "any_r50": "Any R50 swath overlap",
    "share_area_r64": "Share of area in R64 swath",
    "any_r64": "Any R64 swath overlap",
    "rain_total_mean_mm": "Mean cumulative rainfall (mm)",
    "rain_total_max_pixel_mm": "Maximum cumulative rainfall pixel (mm)",
    "rain_total_anomaly_mm": "Mean cumulative rainfall anomaly (mm)",
    "rain_max_daily_mean_mm": "Mean maximum daily rainfall (mm)",
    "rain_max_daily_max_pixel_mm": "Maximum daily rainfall pixel (mm)",
    "rain_max_daily_anomaly_mm": "Mean maximum daily rainfall anomaly (mm)",
    "rain_pixel_count": "CHIRPS pixels in municipality",
}


SOURCES = {
    "ntl": "DMSP-OLS/GAUL",
    "pre": "DMSP-OLS/GAUL",
    "track": "IBTrACS",
    "exposure": "IBTrACS/EBTRK",
    "chirps": "CHIRPS/GAUL",
}


def read_stats(filename: str, source: str) -> list[dict[str, str]]:
    path = PUB_TABLES / filename
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["label"] = LABELS.get(row["variable"], row["variable"])
        row["source"] = source
    return rows


def read_coverage() -> list[dict[str, str]]:
    path = PUB_TABLES / "ntl_country_coverage_publication.csv"
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def numeric_value(value: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        x = float(value)
    except ValueError:
        return None
    if math.isnan(x):
        return None
    return x


def fmt_num(value: str, integer: bool = False) -> str:
    x = numeric_value(value)
    if x is None:
        return ""
    if integer:
        return f"{int(round(x)):,}"
    if abs(x) < 1e-12:
        return "0"
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 100:
        return f"{x:,.1f}"
    if ax >= 10:
        return f"{x:,.2f}"
    if ax >= 1:
        return f"{x:,.3f}"
    if ax >= 0.01:
        return f"{x:,.4f}"
    return f"{x:,.5f}"


def stat_row(row: dict[str, str]) -> list[str]:
    return [
        row["label"],
        fmt_num(row.get("mean", "")),
        fmt_num(row.get("sd", "")),
        fmt_num(row.get("p10", "")),
        fmt_num(row.get("p25", "")),
        fmt_num(row.get("p50", "")),
        fmt_num(row.get("p75", "")),
        fmt_num(row.get("p90", "")),
        fmt_num(row.get("n", ""), integer=True),
        row["source"],
    ]


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def cell(text: str, style: str, pstyle: str, colspan: int = 1) -> str:
    span = f' table:number-columns-spanned="{colspan}"' if colspan > 1 else ""
    covered = "".join("<table:covered-table-cell/>" for _ in range(colspan - 1))
    return (
        f'<table:table-cell table:style-name="{style}" office:value-type="string"{span}>'
        f'<text:p text:style-name="{pstyle}">{esc(text)}</text:p>'
        f"</table:table-cell>{covered}"
    )


def odt_row(values: list[str], style: str = "Cell", pstyle: str = "CellText", numeric_from: int = 1) -> str:
    parts = ["<table:table-row>"]
    for i, value in enumerate(values):
        p = "CellNum" if i >= numeric_from and i < len(values) - 1 else pstyle
        if i == len(values) - 1:
            p = "CellText"
        parts.append(cell(value, style, p))
    parts.append("</table:table-row>")
    return "".join(parts)


def odt_header() -> str:
    row1 = (
        "<table:table-row>"
        + cell("", "HeaderTop", "CellText", colspan=3)
        + cell("Percentile", "HeaderPercentile", "HeaderText", colspan=5)
        + cell("", "HeaderTop", "CellText", colspan=2)
        + "</table:table-row>"
    )
    row2 = odt_row(HEADER_2, "HeaderBottom", "HeaderText")
    return row1 + row2


def odt_section(label: str) -> str:
    return "<table:table-row>" + cell(label, "SectionCell", "SectionText", colspan=len(COLUMNS)) + "</table:table-row>"


def odt_summary_table(title: str, rows: list[list[str] | str], note: str) -> str:
    parts = [
        f'<text:p text:style-name="TableTitle">{esc(title)}</text:p>',
        '<table:table table:name="' + esc(title[:24].replace(" ", "_")) + '">',
    ]
    for idx in range(len(COLUMNS)):
        parts.append(f'<table:table-column table:style-name="Col{idx + 1}"/>')
    parts.append(odt_header())
    data_rows = [r for r in rows if not isinstance(r, str)]
    last_data_idx = len(data_rows) - 1
    seen_data = 0
    for row in rows:
        if isinstance(row, str):
            parts.append(odt_section(row))
            continue
        style = "BottomCell" if seen_data == last_data_idx else "Cell"
        parts.append(odt_row(row, style=style))
        seen_data += 1
    parts.append("</table:table>")
    parts.append(f'<text:p text:style-name="NoteText"><text:span text:style-name="NoteLabel">Notes:</text:span> {esc(note)}</text:p>')
    parts.append('<text:p text:style-name="Spacer"/>')
    return "".join(parts)


def odt_simple_table(title: str, headers: list[str], rows: list[list[str]], note: str) -> str:
    parts = [
        f'<text:p text:style-name="TableTitle">{esc(title)}</text:p>',
        '<table:table table:name="' + esc(title[:24].replace(" ", "_")) + '">',
    ]
    for idx in range(len(headers)):
        parts.append(f'<table:table-column table:style-name="SCol{idx + 1}"/>')
    parts.append(odt_row(headers, style="HeaderBottom", pstyle="HeaderText", numeric_from=1))
    for idx, row in enumerate(rows):
        style = "BottomCell" if idx == len(rows) - 1 else "Cell"
        parts.append(odt_row(row, style=style, numeric_from=1))
    parts.append("</table:table>")
    parts.append(f'<text:p text:style-name="NoteText"><text:span text:style-name="NoteLabel">Notes:</text:span> {esc(note)}</text:p>')
    parts.append('<text:p text:style-name="Spacer"/>')
    return "".join(parts)


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def tex_summary_table(title: str, rows: list[list[str] | str], note: str) -> str:
    lines = [
        r"\begin{table}[!htbp]\centering",
        rf"\caption{{{tex_escape(title)}}}",
        r"\begin{tabular}{lrrrrrrr rl}",
        r"\toprule",
        r" & Mean & SD & \multicolumn{5}{c}{Percentile} & $N$ & Source \\",
        r"\cmidrule(lr){4-8}",
        r" & & & 10 & 25 & 50 & 75 & 90 & & \\",
        r"\midrule",
    ]
    for row in rows:
        if isinstance(row, str):
            lines.append(rf"\multicolumn{{10}}{{l}}{{\emph{{{tex_escape(row)}}}}} \\")
            continue
        lines.append(" & ".join(tex_escape(x) for x in row) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            rf"\multicolumn{{10}}{{p{{0.93\linewidth}}}}{{\emph{{Notes:}} {tex_escape(note)}}} \\",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def tex_simple_table(title: str, headers: list[str], rows: list[list[str]], note: str) -> str:
    lines = [
        r"\begin{table}[!htbp]\centering",
        rf"\caption{{{tex_escape(title)}}}",
        r"\begin{tabular}{lrl}",
        r"\toprule",
        " & ".join(tex_escape(h) for h in headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(tex_escape(x) for x in row) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            rf"\multicolumn{{3}}{{p{{0.72\linewidth}}}}{{\emph{{Notes:}} {tex_escape(note)}}} \\",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def build_tables() -> tuple[list[dict[str, object]], list[str]]:
    ntl_raw = read_stats("ntl_raw_publication_stats.csv", SOURCES["ntl"])
    ntl_pre = read_stats("ntl_pretrend_publication_stats.csv", SOURCES["pre"])
    track = read_stats("besttrack_track_publication_stats.csv", SOURCES["track"])
    exposure = read_stats("besttrack_exposure_publication_stats.csv", SOURCES["exposure"])
    chirps = read_stats("chirps_publication_stats.csv", SOURCES["chirps"])

    ntl_rows = [stat_row(r) for r in ntl_raw] + [stat_row(r) for r in ntl_pre]

    coverage_rows: list[list[str]] = []
    for row in read_coverage():
        coverage_rows.append(
            [
                row["ADM0_NAME"],
                fmt_num(row["municipalities"], integer=True),
                "DMSP-OLS/GAUL",
            ]
        )

    best_rows: list[list[str] | str] = ["Storm-track observations:"]
    best_rows.extend(stat_row(r) for r in track)
    best_rows.append("Municipality exposure measures:")
    best_rows.extend(stat_row(r) for r in exposure)

    chirps_rows = [stat_row(r) for r in chirps]

    tables = [
        {
            "kind": "summary",
            "title": "TABLE 1--DMSP NIGHTTIME LIGHTS SUMMARY STATISTICS",
            "rows": ntl_rows,
            "note": (
                "The first two rows use raw municipality-satellite-year observations. "
                "The pre-period row collapses stable lights to municipality means for 1992-1998. "
                "Pixels are assigned to GAUL level-2 municipalities."
            ),
        },
        {
            "kind": "simple",
            "title": "TABLE 2--DMSP MUNICIPALITY COVERAGE BY COUNTRY",
            "headers": ["Country", "Municipalities", "Source"],
            "rows": coverage_rows,
            "note": (
                "The table reports the number of GAUL-coded municipalities available in the raw "
                "nighttime-lights extract."
            ),
        },
        {
            "kind": "summary",
            "title": "TABLE 3--MITCH BEST TRACK AND WIND EXPOSURE SUMMARY STATISTICS",
            "rows": best_rows,
            "note": (
                "Track variables are from NOAA IBTrACS. Municipality exposure variables combine the processed "
                "IBTrACS track, Extended Best Track wind radii, and matched administrative boundaries. "
                "Wind is measured in knots; distances are kilometers."
            ),
        },
        {
            "kind": "summary",
            "title": "TABLE 4--CHIRPS RAINFALL EXPOSURE SUMMARY STATISTICS",
            "rows": chirps_rows,
            "note": (
                "Rainfall is measured in millimeters for October 27-November 4, 1998. "
                "Anomaly rows subtract the same-calendar-day climatology stack. "
                "Missing rainfall statistics occur where the supplied CHIRPS raster has no valid pixels."
            ),
        },
    ]

    tex_parts = [
        r"% Publication-style tables generated from Stata CSVs.",
        r"% Requires: \usepackage{booktabs}",
        "",
    ]
    for table in tables:
        if table["kind"] == "simple":
            tex_parts.append(tex_simple_table(table["title"], table["headers"], table["rows"], table["note"]))
        else:
            tex_parts.append(tex_summary_table(table["title"], table["rows"], table["note"]))
    return tables, tex_parts


def content_xml(tables: list[dict[str, object]]) -> str:
    xml_parts = []
    for t in tables:
        if t["kind"] == "simple":
            xml_parts.append(odt_simple_table(t["title"], t["headers"], t["rows"], t["note"]))
        else:
            xml_parts.append(odt_summary_table(t["title"], t["rows"], t["note"]))
    table_xml = "".join(xml_parts)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    office:version="1.2">
  <office:font-face-decls>
    <style:font-face style:name="Times New Roman" style:font-family-generic="roman" style:font-pitch="variable"/>
  </office:font-face-decls>
  <office:automatic-styles>
    <style:style style:name="TableTitle" style:family="paragraph">
      <style:paragraph-properties fo:text-align="center" fo:margin-top="0.12in" fo:margin-bottom="0.06in"/>
      <style:text-properties style:font-name="Times New Roman" fo:font-size="11pt" fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="CellText" style:family="paragraph">
      <style:paragraph-properties fo:text-align="start" fo:margin="0in"/>
      <style:text-properties style:font-name="Times New Roman" fo:font-size="9.5pt"/>
    </style:style>
    <style:style style:name="CellNum" style:family="paragraph">
      <style:paragraph-properties fo:text-align="end" fo:margin="0in"/>
      <style:text-properties style:font-name="Times New Roman" fo:font-size="9.5pt"/>
    </style:style>
    <style:style style:name="HeaderText" style:family="paragraph">
      <style:paragraph-properties fo:text-align="center" fo:margin="0in"/>
      <style:text-properties style:font-name="Times New Roman" fo:font-size="9.5pt"/>
    </style:style>
    <style:style style:name="SectionText" style:family="paragraph">
      <style:paragraph-properties fo:text-align="start" fo:margin="0in"/>
      <style:text-properties style:font-name="Times New Roman" fo:font-size="9.5pt" fo:font-style="italic"/>
    </style:style>
    <style:style style:name="NoteText" style:family="paragraph">
      <style:paragraph-properties fo:text-align="start" fo:margin-top="0.04in" fo:margin-bottom="0.05in"/>
      <style:text-properties style:font-name="Times New Roman" fo:font-size="9pt"/>
    </style:style>
    <style:style style:name="NoteLabel" style:family="text">
      <style:text-properties fo:font-style="italic"/>
    </style:style>
    <style:style style:name="Spacer" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0.05in" fo:margin-bottom="0.05in"/>
    </style:style>
    <style:style style:name="Cell" style:family="table-cell">
      <style:table-cell-properties fo:border="none" fo:padding-left="0.03in" fo:padding-right="0.03in" fo:padding-top="0.015in" fo:padding-bottom="0.015in"/>
    </style:style>
    <style:style style:name="HeaderTop" style:family="table-cell">
      <style:table-cell-properties fo:border="none" fo:border-top="0.75pt solid #000000" fo:padding="0.025in"/>
    </style:style>
    <style:style style:name="HeaderPercentile" style:family="table-cell">
      <style:table-cell-properties fo:border="none" fo:border-top="0.75pt solid #000000" fo:border-bottom="0.50pt solid #000000" fo:padding="0.025in"/>
    </style:style>
    <style:style style:name="HeaderBottom" style:family="table-cell">
      <style:table-cell-properties fo:border="none" fo:border-bottom="0.50pt solid #000000" fo:padding-left="0.03in" fo:padding-right="0.03in" fo:padding-top="0.015in" fo:padding-bottom="0.025in"/>
    </style:style>
    <style:style style:name="SectionCell" style:family="table-cell">
      <style:table-cell-properties fo:border="none" fo:padding-left="0.03in" fo:padding-right="0.03in" fo:padding-top="0.055in" fo:padding-bottom="0.015in"/>
    </style:style>
    <style:style style:name="BottomCell" style:family="table-cell">
      <style:table-cell-properties fo:border="none" fo:border-bottom="0.75pt solid #000000" fo:padding-left="0.03in" fo:padding-right="0.03in" fo:padding-top="0.015in" fo:padding-bottom="0.025in"/>
    </style:style>
    <style:style style:name="Col1" style:family="table-column"><style:table-column-properties style:column-width="2.15in"/></style:style>
    <style:style style:name="Col2" style:family="table-column"><style:table-column-properties style:column-width="0.58in"/></style:style>
    <style:style style:name="Col3" style:family="table-column"><style:table-column-properties style:column-width="0.58in"/></style:style>
    <style:style style:name="Col4" style:family="table-column"><style:table-column-properties style:column-width="0.49in"/></style:style>
    <style:style style:name="Col5" style:family="table-column"><style:table-column-properties style:column-width="0.49in"/></style:style>
    <style:style style:name="Col6" style:family="table-column"><style:table-column-properties style:column-width="0.49in"/></style:style>
    <style:style style:name="Col7" style:family="table-column"><style:table-column-properties style:column-width="0.49in"/></style:style>
    <style:style style:name="Col8" style:family="table-column"><style:table-column-properties style:column-width="0.49in"/></style:style>
    <style:style style:name="Col9" style:family="table-column"><style:table-column-properties style:column-width="0.55in"/></style:style>
    <style:style style:name="Col10" style:family="table-column"><style:table-column-properties style:column-width="0.92in"/></style:style>
    <style:style style:name="SCol1" style:family="table-column"><style:table-column-properties style:column-width="2.65in"/></style:style>
    <style:style style:name="SCol2" style:family="table-column"><style:table-column-properties style:column-width="1.10in"/></style:style>
    <style:style style:name="SCol3" style:family="table-column"><style:table-column-properties style:column-width="1.60in"/></style:style>
  </office:automatic-styles>
  <office:body>
    <office:text>
      <text:p text:style-name="NoteText">These tables use the sparse-rule style common in economics journals: no vertical rules, grouped percentile columns, and table notes directly below each panel.</text:p>
      {table_xml}
    </office:text>
  </office:body>
</office:document-content>
'''


def styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    office:version="1.2">
  <office:styles>
    <style:default-style style:family="paragraph">
      <style:text-properties style:font-name="Times New Roman" fo:font-size="10pt"/>
    </style:default-style>
  </office:styles>
  <office:automatic-styles>
    <style:page-layout style:name="pm1">
      <style:page-layout-properties fo:page-width="8.5in" fo:page-height="11in" fo:margin-top="0.75in" fo:margin-bottom="0.75in" fo:margin-left="0.65in" fo:margin-right="0.65in"/>
    </style:page-layout>
  </office:automatic-styles>
  <office:master-styles>
    <style:master-page style:name="Standard" style:page-layout-name="pm1"/>
  </office:master-styles>
</office:document-styles>
'''


def manifest_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
'''


def meta_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" office:version="1.2">
  <office:meta>
    <meta:generator>Codex reproducible table builder</meta:generator>
    <meta:title>Economics data section summary statistics tables</meta:title>
  </office:meta>
</office:document-meta>
'''


def write_odt(tables: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    content = content_xml(tables)
    ET.fromstring(content)
    ET.fromstring(styles_xml())
    ET.fromstring(manifest_xml())
    ET.fromstring(meta_xml())

    with zipfile.ZipFile(ODT_OUT, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zf.writestr("content.xml", content, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("styles.xml", styles_xml(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("meta.xml", meta_xml(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("META-INF/manifest.xml", manifest_xml(), compress_type=zipfile.ZIP_DEFLATED)


def main() -> None:
    tables, tex_parts = build_tables()
    write_odt(tables)
    TEX_OUT.write_text("\n".join(tex_parts), encoding="utf-8")
    print(f"Wrote {ODT_OUT}")
    print(f"Wrote {TEX_OUT}")


if __name__ == "__main__":
    main()
