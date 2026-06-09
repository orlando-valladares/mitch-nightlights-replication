version 18
clear all
set more off

capture mkdir "working/logs"
capture log close make
capture log using "working/logs/make.log", replace name(make) text
if _rc {
    display as text "working/logs/make.log is already open; continuing with the active Stata batch log."
}

display as text "EC64 nighttime-lights workflow"
display as text "Input: raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv"
display as text "Outcome: stable_sum"

if "$ECON64_PYTHON" == "" {
    if "`c(os)'" == "Windows" {
        global ECON64_PYTHON "python"
    }
    else {
        global ECON64_PYTHON "python3"
    }
}
display as text "Python command: $ECON64_PYTHON"
shell $ECON64_PYTHON working/scripts/check_environment.py
if _rc {
    display as error "Environment check failed. See README.md."
    exit _rc
}

shell $ECON64_PYTHON working/scripts/ensure_packaged_inputs.py
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
