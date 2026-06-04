version 18
clear all
set more off
cd "Z:/home/orlando-valladares/Trabajo/ECON64"
capture log close reghdfe_event
capture mkdir "working/logs"
log using "working/logs/reghdfe_event_tables.log", replace name(reghdfe_event) text
adopath ++ "working/ado"
adopath ++ "working/ado/require_src/src"
adopath ++ "working/ado/ftools_src/src"
adopath ++ "working/ado/reghdfe_src/current-code"
adopath ++ "working/ado/reghdfe_src/src"
capture which reghdfe
if _rc {
    display as error "reghdfe not found. Place reghdfe/ftools ado files in working/ado or install them in the Stata bottle."
    exit 111
}
import delimited using "working/data/processed/reghdfe/event_panel_for_reghdfe.csv", clear varnames(1)

capture program drop run_event
program define run_event
    syntax, Rowlabel(string) Treatvar(name) Prefilter(integer) Yearfe(integer)
    preserve
    display as text "=== `rowlabel' ==="
    if `prefilter' == 1 {
        keep if pre_mean_stable_sum >= 100 & !missing(pre_mean_stable_sum)
    }
    local rhs ""
    foreach pair in 1992_1993 1994_1995 1996_1997 1998_1999 2000_2001 2002_2003 2004_2005 2006_2007 2008_2009 2010_2011 2012_2013 {
        local us = strpos("`pair'", "_")
        local start = real(substr("`pair'", 1, `us' - 1))
        local end = real(substr("`pair'", `us' + 1, .))
        if !( `start' == 1996 & `end' == 1997 ) {
            local v ev_`start'_`end'
            capture drop `v'
            gen double `v' = `treatvar' * inrange(year, `start', `end')
            local rhs `rhs' `v'
        }
    }
    if `yearfe' == 1 {
        reghdfe log_ntl `rhs', absorb(muni_unit_id year) vce(cluster muni_unit_id)
    }
    else {
        reghdfe log_ntl `rhs', absorb(muni_unit_id) vce(cluster muni_unit_id)
    }
    restore
end

run_event, rowlabel("64 kt winds and above") treatvar(t_r64) prefilter(0) yearfe(0)
run_event, rowlabel("64 kt with year FE") treatvar(t_r64) prefilter(0) yearfe(1)
run_event, rowlabel("64 kt NTL above 100 and year FE") treatvar(t_r64) prefilter(1) yearfe(1)
run_event, rowlabel("50 kt winds and above") treatvar(t_r50) prefilter(0) yearfe(0)
run_event, rowlabel("50 kt with year FE") treatvar(t_r50) prefilter(0) yearfe(1)
run_event, rowlabel("50 kt NTL above 100 and year FE") treatvar(t_r50) prefilter(1) yearfe(1)
run_event, rowlabel("34 kt winds and above") treatvar(t_r34) prefilter(0) yearfe(0)
run_event, rowlabel("34 kt with year FE") treatvar(t_r34) prefilter(0) yearfe(1)
run_event, rowlabel("34 kt NTL above 100 and year FE") treatvar(t_r34) prefilter(1) yearfe(1)
run_event, rowlabel("Mahajan-Parag point exposure index SD") treatvar(c_mpz) prefilter(0) yearfe(1)
run_event, rowlabel("CHIRPS max-rainfall anomaly top decile") treatvar(t_chirps) prefilter(0) yearfe(1)
run_event, rowlabel("Deaths per capita top decile state-level") treatvar(t_death) prefilter(0) yearfe(1)
run_event, rowlabel("50 kt municipal coverage share") treatvar(c_r50) prefilter(0) yearfe(1)
log close reghdfe_event
