# Mitch Nightlights Replication

Replication materials for *Lost to Mitch: Evidence from Nightlight Years and Hurricane Exposure in Central American Municipalities*.

The repository contains the data, cleaning code, analysis code, paper source, and generated tables and figures needed to reproduce the submitted project. The main entry point is `make.do`.

## Quick Start

1. Download or clone this repository and open Stata from the repository root.
2. Install Python 3.11 or newer and the required packages:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. In Stata, run:

   ```stata
   do make.do
   ```

`make.do` runs `analyze.do` and `graph.do`. It restores the two packaged compressed boundary files, rebuilds the municipality attributes and panel, estimates the final specifications, and recreates the paper assets. On Windows it calls `python`; on macOS and Linux it calls `python3`. A different executable can be selected before running with, for example, `global ECON64_PYTHON "py -3"`.

## Main Outputs

- Final paper source: `paper/main.tex`
- Paper figures and LaTeX table fragments: `paper/Paper_Figures/`
- Processed analysis data: `working/data/processed/`
- Review copies of results, tables, and figures: `out/`
- Run logs: `working/logs/`

The LaTeX paper uses `biblatex` with Biber. Compile from `paper/` after running the pipeline.

## Workflow

- `make.do`: master Stata entry point.
- `analyze.do`: runs municipality construction, the nightlight panel, the merged analysis panel, and final regression tables.
- `graph.do`: runs final summary tables, maps, event studies, annual specifications, the census robustness check, and the CHIRPS descriptive figure.
- `working/scripts/pipeline_engine.py`: shared construction, estimation, table, and figure functions.
- `working/scripts/build_01_*.py` through `build_06_*.py`: ordered analysis stages.
- `working/scripts/source_prep/`: source-specific preparation and optional licensed-data rebuild scripts.

The active `make.do` path is intentionally narrower than the exploratory work history: it produces the specifications and assets used in the final paper rather than every regression considered during development.

## IPUMS Data

The raw IPUMS International fixed-width extract is not included. IPUMS licenses microdata to registered users and does not permit redistribution of the extract to third parties. The public replication therefore includes disclosure-safe, municipality-group-by-year aggregates in `working/data/replication_inputs/ipums_honduras/`; the smallest underlying household cell contains 174 sampled households. These aggregates are sufficient to reproduce the paper's census tables, refrigerator and television coefficients, standard errors, and appendix figure when `make.do` is run.

A licensed user can recreate those aggregate inputs by obtaining the Honduras extract described below, placing it at `raw/dwelling/ipumsi_00003.dat`, and running:

```bash
python working/scripts/source_prep/11_build_ipums_replication_inputs.py
```

The raw file and its local codebook remain ignored by Git.

## Lost in Translation

The main thing lost in translation from the author's machine to a public packet is the raw 632 MB IPUMS microdata extract: it is both too large for an ordinary GitHub file and, more importantly, restricted by the IPUMS user license. I therefore kept the exact cleaning script and extract specification but distributed only the small weighted aggregates used by the final paper; this makes `make.do` reproducible for the reported census results while acknowledging that a fully licensed rebuild may differ at the last floating-point decimal across Python or library versions. Large spatial inputs create a related practical difficulty, so the two largest required analytical boundary files are stored as tracked gzip archives and restored automatically at the start of the build.

## Data Inventory

Source files under `raw/` are immutable. Intermediate data live under `working/`, and final outputs live under `out/` and `paper/Paper_Figures/`.

### Publicly Packaged Inputs

- `raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv`: NOAA DMSP-OLS municipality-year stable lights and cloud-free coverage fields.
- `raw/external/ebtrk_atlc_1851_2021.txt`: NOAA Extended Best Track data used to build the Mitch 34-, 50-, and 64-knot wind swaths.
- `raw/external/ibtracs.NA.list.v04r01.csv`: NOAA IBTrACS track metadata and checks.
- `raw/external/geoboundaries_adm*.geojson`: geoBoundaries administrative geometry used in matching and maps.
- `raw/chirps_mitch_daily_stack_19981027_19981104_ca5.tif`: nine-day CHIRPS Mitch rainfall stack.
- `raw/chirps_climatology_stack_1981_present_oct27_nov04_ca5.tif`: same-calendar-day CHIRPS climatology.
- `raw/mitch_subnational_impacts.csv` and `raw/orlando_custom_mitch.xlsx`: compiled Mitch mortality and supporting exposure data.
- `working/data/processed/municipalities_adm2_analytical.geojson.gz` and `working/data/processed/did_dashboard/gaul_name_matched_municipalities_analytical.geojson.gz`: project-built analytical boundary archives restored automatically by `ensure_packaged_inputs.py`.

Source-preparation scripts and matching registries are under `working/scripts/source_prep/` and `working/municipality_boundary_match_registry.*`.

### IPUMS Extract Specification

The raw IPUMS file is intentionally absent under the [IPUMS International terms of use](https://www.ipums.org/about/terms). The final paper uses Honduras census samples for 1988, 2001, and 2013. The broader local extract also contains 1961 and 1974. Final-paper variables are `YEAR`, `SAMPLE`, `SERIAL`, `HHWT`, `GEO2_HN`, `OWNERSHIP`, `ELECTRIC`, `WATSUP`, `SEWAGE`, `FUELCOOK`, `REFRIG`, `TV`, `ROOMS`, `BEDROOMS`, `TOILET`, `FLOOR`, `WALL`, `ROOF`, `HHTYPE`, `PERNUM`, `PERWT`, `AGE`, `EDATTAIN`, `YRSCHOOL`, and `CLASSWK`.

The fixed-width column positions are declared in `working/scripts/source_prep/11_build_ipums_replication_inputs.py`. A licensed extract should be placed at `raw/dwelling/ipumsi_00003.dat` before running that script.

The distributed aggregate inputs are:

- `households.csv`: 2,727 weighted group-year cells for nine dwelling and asset measures.
- `honduras_50kt_population_education.csv`: 18 population, schooling, and worker-type summary rows.
- `honduras_50kt_dwelling_summary.csv`: 24 target-group and national dwelling summary rows.
- `honduras_50kt_ipums_geography_crosswalk.csv`: 16 treated-municipality-to-IPUMS-group crosswalk rows.

All four files are in `working/data/replication_inputs/ipums_honduras/`. No person- or household-level records are distributed.

### Local-Only Inputs

- `raw/GAUL_2024_L2.shp`: approximately 739 MB and ignored; the public pipeline uses the compressed analytical boundary archives.
- `raw/dwelling/ipumsi_00003.dat`: approximately 632 MB, licensed, ignored, and not redistributable.
- `raw/dwelling/EC64_IPUMScodebook.md`: ignored because the local export included private extract metadata; the required layout is recorded in the source-preparation script.

## Bottles Note

The author's Stata 18 installation runs inside a Linux Bottles/Wine environment. Windows Stata in that bottle cannot directly see the host Linux Python executable, although native Windows Stata with Windows Python and native macOS/Linux Stata work with the dispatch in `make.do`. On a similar Bottles setup, run the Python stages from the host terminal or install Python and the requirements inside the bottle; this environment boundary does not change the code or results.

## Expected Runtime

Runtime depends mainly on geospatial I/O and figure rendering. The raw IPUMS rebuild is optional and substantially slower; the ordinary public replication uses the packaged aggregates and does not read the restricted microdata.
