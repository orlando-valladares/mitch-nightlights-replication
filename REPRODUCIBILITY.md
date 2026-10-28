# Reproducibility

## Environment verified on 2026-10-28

- Linux
- StataNow 19.5 BE running code declared with `version 18`
- Python 3 with the packages in `requirements.txt`
- LaTeX with `pdflatex`; the paper additionally uses Biber

## A. Rebuild from source inputs

Status: **partial**. The geospatial and nightlight construction scripts are present under `working/scripts/source_prep/` and `working/scripts/build_01_*.py` through `build_03_*.py`. Publicly packaged storm, rainfall, boundary, and nightlight inputs are included or restored from tracked compressed files. The raw IPUMS International microdata are not redistributed; licensed users must supply their own extract for a household-level census rebuild.

The historical full build remains:

```bash
stata -b do make.do
```

This path depends on Python and geospatial libraries. In the audited environment, the direct Python stages completed, but Stata's shell wrapper returned `r(693)` after a successful Python stage. For that environment, run the ordered Python stages directly as documented in their file headers.

## B. Reproduce from the analysis-ready panels

Status: **verified**.

```bash
stata -b do code/00_master.do
python3 code/03_render_stata_outputs.py
```

Inputs:

- `working/data/processed/analysis_panel_main.csv`
- `working/data/processed/state_year_panel_deaths.csv`

Expected outputs:

- `out/results/stata/mitch_event_study_results.csv`
- `out/results/stata/mitch_event_study_results.dta`
- `out/results/tables/structured/main_results/regression_tables/event_study/*.tex`
- `out/results/figures/structured/main_results/figures/event_study/year_fe_ntl_filter/*.png`

The Stata run completed in approximately 25 seconds and the renderer in approximately 7 seconds on the audit machine. These are measurements, not hardware-independent expectations.

## C. Reviewer fast path

Status: **verified**.

```bash
stata -b do coding-sample/stata_coding_sample.do
```

This validates the preferred real-data sample and reproduces the 64- and 50-knot two-year event-study estimates in `out/results/stata/preferred_wind_event_study.csv`. It does not fabricate or simulate data.

## External inputs and terms

| Input | Use | Redistribution status |
|---|---|---|
| DMSP-OLS stable lights | Municipality-year outcome | Public; source attribution retained |
| NOAA EBTRK / IBTrACS | Track and wind radii | Public/open access |
| CHIRPS | Mitch rainfall anomaly | Public-domain/CC0-style distribution |
| geoBoundaries gbOpen | Administrative geometry | CC BY 4.0 |
| IPUMS International | Census appendix | Raw microdata restricted; only aggregates included |
| Compiled mortality reports | State-level exposure | Included project compilation; source trail in project files |

## Clean rerun checks

Run the Stata master twice. `mitch_event_study_results.csv` should be byte-identical because it contains no timestamps or randomized operations. Then run:

```bash
stata -b do tests/01_smoke_test.do
python3 tests/02_static_checks.py
```

Stata's batch executable can return shell status zero even when a do-file ends with an error. Check the log for `Stata estimation completed successfully.` and the presence of the expected output files; the smoke test enforces numerical and structural checks.
