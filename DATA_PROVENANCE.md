# Data Provenance

| Stage | Important paths | Produced by / source | Downstream use |
|---|---|---|---|
| Raw nightlights | `raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv` | DMSP-OLS extract | Annual municipality outcome |
| Storm track and radii | `raw/external/ebtrk_atlc_1851_2021.txt`, `raw/external/ibtracs.NA.list.v04r01.csv` | NOAA EBTRK and IBTrACS | Wind swaths and track checks |
| Rainfall | `raw/chirps_mitch_daily_stack_19981027_19981104_ca5.tif`, climatology stack | CHIRPS | Rainfall anomaly exposure |
| Boundaries | `raw/external/geoboundaries_adm*.geojson` and tracked analytical `.geojson.gz` files | geoBoundaries plus project crosswalk | Municipality geometry and aggregation |
| Mortality | `raw/mitch_subnational_impacts.csv`, `raw/orlando_custom_mitch.xlsx` | Compiled historical reports | State exposure |
| Matching | `working/municipality_boundary_match_registry.csv` | Audited project crosswalk | Retained municipality universe |
| Municipality attributes | `working/data/processed/municipality_attributes.csv` | `working/scripts/build_01_municipality_attributes.py` | Treatment assignment |
| Nightlight panel | `working/data/processed/did_dashboard/ntl_municipality_year_panel.csv` | source-preparation scripts | Outcome construction |
| Analysis panel | `working/data/processed/analysis_panel_main.csv` | `working/scripts/build_03_analysis_panel.py` | Stata municipality regressions |
| Mortality panel | `working/data/processed/state_year_panel_deaths.csv` | project panel builder | Stata state regressions |
| Estimates | `out/results/stata/mitch_event_study_results.*` | `code/02_estimate_mitch.do` | Tables and figures |
| Presentation assets | `out/results/`, `paper/Paper_Figures/` | `code/03_render_stata_outputs.py` | Paper and reviewer outputs |

The raw-download manifest contains historical machine-specific paths. They are provenance records, not active dependencies. The active Stata path uses repository-relative files only.
