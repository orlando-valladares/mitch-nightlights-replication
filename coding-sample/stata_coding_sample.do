version 18
clear all
set more off

* Run from the repository root.
local panel "working/data/processed/analysis_panel_main.csv"
local output "out/results/stata/preferred_wind_event_study.csv"
local ntl_cutoff 101.79

capture confirm file "`panel'"
if _rc {
    display as error "Missing analysis panel: `panel'"
    exit 601
}

import delimited using "`panel'", clear varnames(1)
confirm variable muni_unit_id year log_ntl pre_mean_stable_sum
confirm variable ebtrk_treat50_r64_all ebtrk_treat50_r50_all

* The panel must be balanced and uniquely identified before estimation.
isid muni_unit_id year
assert inrange(year, 1992, 2013)
assert !missing(muni_unit_id, year, log_ntl, pre_mean_stable_sum)
bysort muni_unit_id: assert _N == 22

* This restriction uses only the six pre-treatment years, 1992-1997.
keep if pre_mean_stable_sum >= `ntl_cutoff'
quietly count
assert r(N) == 10956

tempfile estimates
tempname results
postfile `results' str4 wind int period_start period_end double coefficient ///
    std_error p_value ci_low ci_high long observations clusters using `estimates', replace

foreach wind in r64 r50 {
    local treatment ebtrk_treat50_`wind'_all
    bysort muni_unit_id: assert `treatment' == `treatment'[1]

    local event_terms
    foreach period in 1992_1993 1994_1995 1998_1999 2000_2001 2002_2003 ///
        2004_2005 2006_2007 2008_2009 2010_2011 2012_2013 {
        gettoken start end : period, parse("_")
        local end = subinstr("`end'", "_", "", .)
        generate double event_`start'_`end' = ///
            `treatment' * inrange(year, `start', `end')
        local event_terms `event_terms' event_`start'_`end'
    }

    * 1996-1997 is omitted. Municipality and year effects are absorbed;
    * inference is clustered at the municipality level.
    quietly areg log_ntl `event_terms' i.year, ///
        absorb(muni_unit_id) vce(cluster muni_unit_id)

    local residual_df = e(df_r)
    local critical = invttail(`residual_df', 0.025)
    foreach period in 1992_1993 1994_1995 1998_1999 2000_2001 2002_2003 ///
        2004_2005 2006_2007 2008_2009 2010_2011 2012_2013 {
        gettoken start end : period, parse("_")
        local end = subinstr("`end'", "_", "", .)
        local term event_`start'_`end'
        local b = _b[`term']
        local se = _se[`term']
        local p = 2 * ttail(`residual_df', abs(`b' / `se'))
        post `results' ("`wind'") (`start') (`end') (`b') (`se') (`p') ///
            (`b' - `critical' * `se') (`b' + `critical' * `se') ///
            (e(N)) (e(N_clust))
    }
    post `results' ("`wind'") (1996) (1997) (0) (.) (.) (.) (.) ///
        (e(N)) (e(N_clust))
    drop event_*
}

postclose `results'
use `estimates', clear
sort wind period_start
isid wind period_start period_end
export delimited using "`output'", replace

display as result "Preferred wind event studies exported to `output'."
