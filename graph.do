version 18
clear all
set more off

* Run from the project root.
* Builds the final paper tables, maps, figures, and census robustness assets.

capture log close graph
capture mkdir "working/logs"
log using "working/logs/graph_assignment.log", replace name(graph) text

if "$ECON64_PYTHON" == "" {
    if "`c(os)'" == "Windows" {
        global ECON64_PYTHON "python"
    }
    else {
        global ECON64_PYTHON "python3"
    }
}

display as text "Building final paper tables, figures, and maps."
shell $ECON64_PYTHON working/scripts/build_05_tables_figures.py
if _rc {
    display as error "Tables/figures build failed."
    exit _rc
}

display as text "Building IPUMS census robustness outputs from packaged aggregates."
shell $ECON64_PYTHON working/scripts/build_06_census_robustness.py
if _rc {
    display as error "Census robustness build failed."
    exit _rc
}

display as text "Building CHIRPS descriptive figure."
shell $ECON64_PYTHON working/scripts/source_prep/10_build_chirps_descriptive_figures.py
if _rc {
    display as error "CHIRPS descriptive figure build failed."
    exit _rc
}

display as text "Verifying final paper assets and reported census results."
shell $ECON64_PYTHON working/scripts/verify_replication_outputs.py
if _rc {
    display as error "Replication output verification failed."
    exit _rc
}

display as text "Paper outputs written to paper/Paper_Figures and out/."
log close graph
