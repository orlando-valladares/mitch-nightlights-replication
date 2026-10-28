version 18

capture confirm file "working/data/processed/analysis_panel_main.csv"
if _rc {
    display as error "Missing analysis panel: working/data/processed/analysis_panel_main.csv"
    exit 601
}

import delimited using "working/data/processed/analysis_panel_main.csv", clear varnames(1)

confirm variable muni_unit_id year log_ntl stable_sum pre_mean_stable_sum
confirm variable ebtrk_treat50_r64_all ebtrk_treat50_r50_all
confirm variable chirps_max_anomaly_top10

assert !missing(muni_unit_id, year, log_ntl, stable_sum, pre_mean_stable_sum)
assert inrange(year, 1992, 2013)
assert stable_sum >= 0
isid muni_unit_id year

quietly count
assert r(N) == 21912
quietly levelsof year, local(panel_years)
assert "`panel_years'" == "1992 1993 1994 1995 1996 1997 1998 1999 2000 2001 2002 2003 2004 2005 2006 2007 2008 2009 2010 2011 2012 2013"

bysort muni_unit_id: assert _N == 22
bysort muni_unit_id: assert pre_mean_stable_sum == pre_mean_stable_sum[1]

quietly count if stable_sum == 0
display as text "Municipality-year zero stable-light observations: " r(N)
quietly count if pre_mean_stable_sum >= 101.79
assert r(N) == 10956
display as text "Preferred-sample municipality-years: " r(N)

foreach treatment in ebtrk_treat50_r64_all ebtrk_treat50_r50_all ///
    ebtrk_treat50_r34_all chirps_max_anomaly_top10 rain50_chirps_top10 {
    assert inlist(`treatment', 0, 1)
    bysort muni_unit_id: assert `treatment' == `treatment'[1]
}

capture confirm file "working/data/processed/state_year_panel_deaths.csv"
if _rc {
    display as error "Missing state panel: working/data/processed/state_year_panel_deaths.csv"
    exit 601
}

import delimited using "working/data/processed/state_year_panel_deaths.csv", clear varnames(1)
confirm variable muni_unit_id year log_ntl stable_sum pre_mean_stable_sum death_pc_top10_state
assert !missing(muni_unit_id, year, log_ntl, stable_sum, pre_mean_stable_sum, death_pc_top10_state)
assert inrange(year, 1992, 2013)
assert inlist(death_pc_top10_state, 0, 1)
isid muni_unit_id year
quietly count
assert r(N) == 1584
bysort muni_unit_id: assert _N == 22
bysort muni_unit_id: assert death_pc_top10_state == death_pc_top10_state[1]

display as result "Panel checks passed."
