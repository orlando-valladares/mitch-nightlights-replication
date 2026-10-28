version 18
clear all
set more off

capture confirm file "out/results/stata/mitch_event_study_results.csv"
assert _rc == 0

import delimited using "out/results/stata/mitch_event_study_results.csv", clear varnames(1)
isid model treatment panel sample year_fe period_start period_end
assert inlist(sample, "all", "median")
assert inlist(year_fe, 0, 1)

quietly count if model == "twoyear" & period_start == 1996 & period_end == 1997
assert r(N) == 24
assert coefficient == 0 if model == "twoyear" & period_start == 1996 & period_end == 1997
assert missing(std_error) if model == "twoyear" & period_start == 1996 & period_end == 1997

quietly count if model == "twoyear" & treatment == "64kt" & sample == "median" ///
    & year_fe == 1 & period_start == 1998 & observations == 10956 & clusters == 498
assert r(N) == 1

quietly summarize coefficient if model == "twoyear" & treatment == "64kt" ///
    & sample == "median" & year_fe == 1 & period_start == 1998, meanonly
assert abs(r(mean) - (-0.1095531)) < 0.000001

quietly summarize std_error if model == "twoyear" & treatment == "64kt" ///
    & sample == "median" & year_fe == 1 & period_start == 1998, meanonly
assert abs(r(mean) - 0.0435433) < 0.000001

display as result "Stata smoke test passed."
