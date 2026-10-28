version 18
clear all
set more off

* Run from the repository root:
*     stata -b do code/00_master.do

capture mkdir "working/logs"
capture mkdir "out/results/stata"
capture log close _all
log using "working/logs/stata_master.log", replace text

display as text "Hurricane Mitch replication: Stata-first showcase"
display as text "Stata version: `c(stata_version)'"

do "code/01_validate_panel.do"
do "code/02_estimate_mitch.do"

display as result "Stata estimation completed successfully."
display as text "Results: out/results/stata/mitch_event_study_results.csv"
display as text "Render unchanged paper styles with: python3 code/03_render_stata_outputs.py"

log close
