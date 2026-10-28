# Start Here: Reviewer Guide

This package foregrounds a short, native-Stata analysis path while retaining the underlying geospatial construction code.

1. Open [`code/00_master.do`](code/00_master.do) to see the entry point and output contract.
2. Review [`code/01_validate_panel.do`](code/01_validate_panel.do) for key uniqueness, balance, range, treatment, and sample assertions.
3. Read [`code/02_estimate_mitch.do`](code/02_estimate_mitch.do), especially `post_mitch_model`, which constructs the omitted-bin event study, absorbs unit effects, adds year effects, and clusters by panel unit.
4. Inspect [`out/results/stata/mitch_event_study_results.csv`](out/results/stata/mitch_event_study_results.csv), then the principal [table](out/results/tables/structured/main_results/regression_tables/event_study/table_four_treatments_no34.tex) and [figure](out/results/figures/structured/main_results/figures/event_study/year_fe_ntl_filter/fig_four_treatments_no34.png).
5. Use [`working/scripts/source_prep/`](working/scripts/source_prep/) and the ordered Python build scripts only if reviewing construction from raw spatial inputs.

The HTML dashboards are optional AI-assisted exploratory displays. The statistical showcase is Stata-first. Current limitations—including treatment-group size, modern boundaries, satellite averaging, and the interpretation of `log(1 + lights)`—are summarized in [`METHODS_AND_LIMITATIONS.md`](METHODS_AND_LIMITATIONS.md).
