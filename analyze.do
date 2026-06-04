version 18
clear all
set more off

* Run from the project root.
* Reproducible analysis pipeline for canonical panels and regression outputs.

capture log close analyze
capture mkdir "working/logs"
log using "working/logs/analyze_assignment.log", replace name(analyze) text

display as text "Building municipality attributes."
shell python3 working/scripts/build_01_municipality_attributes.py
if _rc {
    display as error "Municipality attributes build failed."
    exit _rc
}

display as text "Building municipality-year panel."
shell python3 working/scripts/build_02_municipality_year_panel.py
if _rc {
    display as error "Municipality-year panel build failed."
    exit _rc
}

display as text "Building analysis panel."
shell python3 working/scripts/build_03_analysis_panel.py
if _rc {
    display as error "Analysis panel build failed."
    exit _rc
}

display as text "Building regression outputs."
shell python3 working/scripts/build_04_regressions.py
if _rc {
    display as error "Regression build failed."
    exit _rc
}

display as text "Analysis outputs written to working/data/processed and out/results."
log close analyze
