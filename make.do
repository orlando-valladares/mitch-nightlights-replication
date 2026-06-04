version 18
clear all
set more off

capture log close make
capture log using "working/logs/make.log", replace name(make) text
if _rc {
    display as text "working/logs/make.log is already open; continuing with the active Stata batch log."
}

display as text "EC64 nighttime-lights workflow"
display as text "Input: raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv"
display as text "Outcome: stable_sum"
shell python3 working/scripts/ensure_packaged_inputs.py
if _rc {
    display as error "Packaged input restore failed."
    exit _rc
}
display as text "Running analyze.do"
do "analyze.do"

display as text "Running graph.do"
do "graph.do"

display as text "Workflow complete"
capture log close make
