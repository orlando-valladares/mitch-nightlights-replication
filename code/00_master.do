version 18
clear all
set more off

*******************************************************************************
* 1. Project setup
*******************************************************************************

* Run from the repository root:
*     stata -b do code/00_master.do

capture mkdir "out/logs"
capture mkdir "out/results"
capture log close _all
log using "out/logs/stata_master.log", replace text

display as text "Hurricane Mitch replication: Stata workflow"
display as text "Stata version: `c(stata_version)'"

*******************************************************************************
* 2. Panel construction, validation, and analysis
*******************************************************************************

do "code/01_build_panel.do"
do "code/02_validate_panel.do"
do "code/03_estimate_mitch.do"

*******************************************************************************
* 3. Handoff
*******************************************************************************

display as result "Stata estimation completed successfully."
display as text "Results: out/results/mitch_event_study_results.csv"
display as text "Coding sample: out/Orlando_Valladares_Stata_Coding_Sample.pdf"

log close
