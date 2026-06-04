version 18
clear all
set more off

* Run from the project root.
* Builds paper tables, maps, figures, and Overleaf presentation assets.

capture log close graph
capture mkdir "working/logs"
log using "working/logs/graph_assignment.log", replace name(graph) text

display as text "Building structured tables, figures, maps, and presentation."
shell python3 working/scripts/build_05_tables_figures.py
if _rc {
    display as error "Tables/figures build failed."
    exit _rc
}

display as text "Graph and Overleaf outputs written by working/scripts/build_05_tables_figures.py."
log close graph
