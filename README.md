# Hurricane Mitch and Municipal Nighttime Lights

This senior seminar replication studies how Hurricane Mitch affected local economic activity in Central America using a 1992–2013 municipality-year panel of DMSP-OLS stable lights and meteorological exposure. The preferred specifications use two-year event-time bins, municipality and year fixed effects, and standard errors clustered by municipality.

[`Coding-sample PDF`](out/Orlando_Valladares_Stata_Coding_Sample.pdf) · [`Stata master`](code/00_master.do) · [`Panel construction`](code/01_build_panel.do) · [`Estimation`](code/03_estimate_mitch.do) · [`Paper source`](out/paper/main.tex)

## Start here

| Order | File | Purpose |
|---:|---|---|
| 1 | [`code/00_master.do`](code/00_master.do) | Runs the documented Stata workflow |
| 2 | [`code/01_build_panel.do`](code/01_build_panel.do) | Cleans nightlights, merges exposure attributes, and checks the panel |
| 3 | [`code/02_validate_panel.do`](code/02_validate_panel.do) | Verifies keys, balance, years, zeros, and treatment variables |
| 4 | [`code/03_estimate_mitch.do`](code/03_estimate_mitch.do) | Estimates and exports the event studies |
| 5 | [`code/coding_sample.do`](code/coding_sample.do) | Standalone 200-line reviewer sample |

The main panel contains 996 municipalities observed annually from 1992 through 2013. The outcome is `ln(1 + stable-light sum)`. Overlapping DMSP satellites are averaged within municipality-year. The preferred sample retains 498 municipalities whose mean stable lights during 1992–1997 are at least 101.79.

In that sample, the 64-knot specification estimates coefficients of −0.110 in 1998–1999 and −0.229 in 2000–2001; the corresponding 50-knot coefficients are −0.168 and −0.228. These are changes in `ln(1 + lights)`, not exact percentage changes in untransformed luminosity.

![Preferred event-study estimates](out/figures/main-event-study.png)

## Reproduce

From the repository root, with Stata 18 or later:

```bash
stata -b do code/00_master.do
```

Reviewer fast path:

```bash
stata -b do code/coding_sample.do
```

Expected machine-readable outputs:

- [`out/results/mitch_event_study_results.csv`](out/results/mitch_event_study_results.csv)
- [`out/results/preferred_wind_event_study.csv`](out/results/preferred_wind_event_study.csv)
- [`out/tables/main-event-study.tex`](out/tables/main-event-study.tex)
- [`out/figures/main-event-study.png`](out/figures/main-event-study.png)

The optional [`wind dashboard`](out/dashboards/wind-dashboard.html) is an AI-assisted exploratory visualization used to inspect newly assembled meteorological data. It is not the estimator and is not required for the Stata reproduction.

## Repository layout

```text
code/   Stata workflow, coding sample, and upstream geospatial source code
data/   Raw public inputs, processed panels, and boundary metadata
out/    Coding PDF, paper source/assets, selected results, and dashboard
```

## Data construction and provenance

The Stata reviewer path starts from:

- `data/raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv`: DMSP-OLS municipality-by-satellite-by-year lights.
- `data/processed/municipality_attributes.csv`: audited municipality wind/rain/mortality attributes.
- `data/processed/state_year_panel_deaths.csv`: state-year mortality panel.

Upstream source code for storm tracks, wind swaths, rainfall, boundary matching, and census aggregates is nested under `code/python/`. Modern administrative boundaries are used rather than a reconstructed 1998 boundary vintage. DMSP satellites are averaged but not intercalibrated.

Wind treatment equals one when at least half of a municipality lies inside the storm-total 50- or 64-knot EBTRK swath. Rainfall treatment identifies the top decile of the maximum CHIRPS anomaly. Mortality exposure is assigned at the state level. The event-study reference period is 1996–1997.

The distributed analysis files do not contain Mahajan–Parag/Yang grid data or derived exposure columns. Related historical discussion may remain in the paper or archived source code, but those data are not part of this public package.

## Data licensing

The repository [`LICENSE`](LICENSE) applies to source code only. Data in `data/` retain their original terms:

- NOAA DMSP-OLS and storm-track products are publicly distributed by their source agencies.
- CHIRPS precipitation products are publicly distributed by the Climate Hazards Center.
- geoBoundaries gbOpen files require attribution under CC BY 4.0.
- IPUMS International microdata are not included. Only disclosure-safe aggregates are distributed; licensed users must obtain their own extract to rebuild those aggregates.

## Limitations

Treatment was not randomly assigned, the preferred wind-treated groups are small, exposure may spill across municipal boundaries, and municipality clustering does not address every form of spatial correlation. Nighttime luminosity is an imperfect proxy for income, particularly in low-light municipalities. The package therefore presents the estimates as transparent descriptive causal evidence subject to these limitations, not as definitive measurement of income losses.

Project-authored code is MIT licensed. Python dependencies for the optional geospatial source code are listed in [`requirements.txt`](requirements.txt).
