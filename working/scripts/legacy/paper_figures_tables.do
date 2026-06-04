version 18
clear all
set more off

* Run from the project root.
capture log close paper
capture mkdir "working/logs"
log using "working/logs/paper_figures_tables.log", replace name(paper) text

capture mkdir "out"
capture mkdir "out/paper_figures"
capture mkdir "working/overleaf/Paper_Figures"

adopath ++ "working/ado"

capture which esttab
if _rc {
    display as error "esttab/estout is required. Install in Stata with: ssc install estout"
    exit 111
}

* ---------------------------------------------------------------------
* Copy paper-source figures into the paper output folder and Overleaf.
* ---------------------------------------------------------------------
copy "out/data/figures/ntl_total_by_country.png" ///
    "out/paper_figures/ntl_total_by_country.png", replace
copy "out/data/figures/ntl_mean_by_satellite.png" ///
    "out/paper_figures/ntl_mean_by_satellite.png", replace
copy "out/data/figures/map_four_treatments_default_bw.png" ///
    "out/paper_figures/map_four_treatments_default_bw.png", replace
copy "out/paper_figures/ntl_total_by_country.png" ///
    "working/overleaf/Paper_Figures/ntl_total_by_country.png", replace
copy "out/paper_figures/ntl_mean_by_satellite.png" ///
    "working/overleaf/Paper_Figures/ntl_mean_by_satellite.png", replace
copy "out/paper_figures/map_four_treatments_default_bw.png" ///
    "working/overleaf/Paper_Figures/map_four_treatments_default_bw.png", replace

* The no-year-FE DiD 4-slot graph is produced by graph.do.
do "graph.do"
copy "out/results/figures/did_annual_combined_4slot.png" ///
    "out/paper_figures/did_annual_combined_4slot_no_year_fe.png", replace
copy "out/paper_figures/did_annual_combined_4slot_no_year_fe.png" ///
    "working/overleaf/Paper_Figures/did_annual_combined_4slot_no_year_fe.png", replace

* ---------------------------------------------------------------------
* Rebuild analysis panels.
* ---------------------------------------------------------------------
import delimited using "out/data/tables/assignment/assignment_municipalities.csv", clear varnames(1) encoding("UTF-8")
destring pre_mean_stable_sum best_default_score yang_default_treated in_selected_country, replace force
keep if in_selected_country == 1
gen byte include_default = !missing(pre_mean_stable_sum) & pre_mean_stable_sum >= 100
tempfile muni
save `muni'

import delimited using "working/data/processed/did_dashboard/ntl_municipality_year_panel.csv", clear varnames(1) encoding("UTF-8")
destring year stable_sum pre_mean_stable_sum, replace force
merge m:1 muni_key using `muni', keep(match) nogen
keep if in_selected_country == 1
keep if inrange(year, 1992, 2013)
gen log_ntl = ln(stable_sum + 1)
egen muni_unit_id = group(muni_key)
tempfile muni_panel
save `muni_panel'

import delimited using "out/data/tables/assignment/assignment_state_year_panel.csv", clear varnames(1) encoding("UTF-8")
destring year stable_sum pre_mean_stable_sum death_score has_death_data deaths_per_capita, replace force
keep if !inlist(country_name, "Costa Rica", "Panama")
keep if inrange(year, 1992, 2013)
gen log_ntl = ln(stable_sum + 1)
gen byte death_include_default = !missing(pre_mean_stable_sum) & pre_mean_stable_sum >= 100 & has_death_data == 1
egen state_unit_id = group(state_key)
tempfile state_panel
save `state_panel'

* ---------------------------------------------------------------------
* DiD regressions: one table, with and without year fixed effects.
* ---------------------------------------------------------------------
capture program drop run_did
program define run_did
    syntax, Name(name) Treatvar(name) Unitvar(name) Timevar(name) Yearfe(integer) Title(string)

    capture drop post treat_post
    gen byte post = `timevar' >= 1998
    gen double treat_post = `treatvar' * post
    label var treat_post "Treated x Post"

    quietly levelsof `unitvar' if `treatvar' == 1, local(tunits)
    quietly levelsof `unitvar' if `treatvar' == 0, local(cunits)
    local nt : word count `tunits'
    local nc : word count `cunits'

    if `yearfe' == 1 {
        areg log_ntl treat_post i.`timevar', absorb(`unitvar') vce(cluster `unitvar')
    }
    else {
        areg log_ntl post treat_post, absorb(`unitvar') vce(cluster `unitvar')
    }
    eststo `name'
    estadd local Treatment "`title'"
    if `yearfe' == 1 {
        estadd local YearFE "Yes"
    }
    else {
        estadd local YearFE "No"
    }
    estadd scalar Treated = `nt'
    estadd scalar Control = `nc'
    drop post treat_post
end

eststo clear
use `muni_panel', clear
keep if include_default
gen byte treat_best = best_default_score >= .5
gen byte treat_yang = yang_default_treated == 1
run_did, name(did_best_no) treatvar(treat_best) unitvar(muni_unit_id) timevar(year) yearfe(0) title("Best Track")
run_did, name(did_best_yfe) treatvar(treat_best) unitvar(muni_unit_id) timevar(year) yearfe(1) title("Best Track")
run_did, name(did_yang_no) treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) yearfe(0) title("Mahajan-Parag")
run_did, name(did_yang_yfe) treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) yearfe(1) title("Mahajan-Parag")

use `state_panel', clear
keep if death_include_default
gen byte treat_death = death_score >= .05
run_did, name(did_death_no) treatvar(treat_death) unitvar(state_unit_id) timevar(year) yearfe(0) title("Deaths per capita")
run_did, name(did_death_yfe) treatvar(treat_death) unitvar(state_unit_id) timevar(year) yearfe(1) title("Deaths per capita")

esttab did_best_no did_best_yfe did_yang_no did_yang_yfe did_death_no did_death_yfe ///
    using "out/paper_figures/regression_table_annual_did.tex", replace booktabs ///
    label keep(*treat_post*) b(3) se(3) star(* 0.10 ** 0.05 *** 0.01) ///
    mtitles("Best Track" "Best Track" "Mahajan-Parag" "Mahajan-Parag" "Deaths/capita" "Deaths/capita") ///
    stats(YearFE N r2 Treated Control, labels("Year FE" "Observations" "R-squared" "Treated units" "Control units")) ///
    title("Annual Difference-in-Differences Estimates, 1992--2013") ///
    addnotes("Outcome is log(1 + DMSP-OLS stable lights). Unit fixed effects are included in all models. Standard errors are clustered by unit.")

copy "out/paper_figures/regression_table_annual_did.tex" ///
    "working/overleaf/Paper_Figures/regression_table_annual_did.tex", replace

* ---------------------------------------------------------------------
* Event-study regressions: year-by-treatment coefficients, 1997 omitted.
* The exported event-study table includes both variants; the graph uses the
* preferred unit-and-year-FE specification.
* ---------------------------------------------------------------------
capture program drop make_event_vars
program define make_event_vars
    syntax, Treatvar(name) Timevar(name)
    capture drop event_*
    forvalues y = 1992/2013 {
        if `y' != 1997 {
            gen double event_`y' = `treatvar' * (`timevar' == `y')
            label var event_`y' "`y'"
        }
    }
end

capture program drop run_event
program define run_event
    syntax, Name(name) Treatvar(name) Unitvar(name) Timevar(name) Yearfe(integer)

    make_event_vars, treatvar(`treatvar') timevar(`timevar')
    local evlist event_1992 event_1993 event_1994 event_1995 event_1996 ///
        event_1998 event_1999 event_2000 event_2001 event_2002 event_2003 ///
        event_2004 event_2005 event_2006 event_2007 event_2008 event_2009 ///
        event_2010 event_2011 event_2012 event_2013

    quietly levelsof `unitvar' if `treatvar' == 1, local(tunits)
    quietly levelsof `unitvar' if `treatvar' == 0, local(cunits)
    local nt : word count `tunits'
    local nc : word count `cunits'

    if `yearfe' == 1 {
        areg log_ntl i.`timevar' `evlist', absorb(`unitvar') vce(cluster `unitvar')
    }
    else {
        areg log_ntl `evlist', absorb(`unitvar') vce(cluster `unitvar')
    }
    eststo `name'
    if `yearfe' == 1 {
        estadd local YearFE "Yes"
    }
    else {
        estadd local YearFE "No"
    }
    estadd scalar Treated = `nt'
    estadd scalar Control = `nc'
end

eststo clear
use `muni_panel', clear
keep if include_default
gen byte treat_best = best_default_score >= .5
gen byte treat_yang = yang_default_treated == 1
run_event, name(ev_best_no) treatvar(treat_best) unitvar(muni_unit_id) timevar(year) yearfe(0)
run_event, name(ev_best_yfe) treatvar(treat_best) unitvar(muni_unit_id) timevar(year) yearfe(1)
run_event, name(ev_yang_no) treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) yearfe(0)
run_event, name(ev_yang_yfe) treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) yearfe(1)

use `state_panel', clear
keep if death_include_default
gen byte treat_death = death_score >= .05
run_event, name(ev_death_no) treatvar(treat_death) unitvar(state_unit_id) timevar(year) yearfe(0)
run_event, name(ev_death_yfe) treatvar(treat_death) unitvar(state_unit_id) timevar(year) yearfe(1)

local evlist event_1992 event_1993 event_1994 event_1995 event_1996 ///
    event_1998 event_1999 event_2000 event_2001 event_2002 event_2003 ///
    event_2004 event_2005 event_2006 event_2007 event_2008 event_2009 ///
    event_2010 event_2011 event_2012 event_2013

esttab ev_best_no ev_best_yfe ev_yang_no ev_yang_yfe ev_death_no ev_death_yfe ///
    using "out/paper_figures/regression_table_annual_event_study.tex", replace booktabs ///
    label keep(`evlist') order(`evlist') b(3) se(3) star(* 0.10 ** 0.05 *** 0.01) ///
    mtitles("Best Track No YFE" "Best Track YFE" "Mahajan-Parag No YFE" "Mahajan-Parag YFE" "Deaths/capita No YFE" "Deaths/capita YFE") ///
    stats(YearFE N r2 Treated Control, labels("Year FE" "Observations" "R-squared" "Treated units" "Control units")) ///
    title("Annual Event-Study Estimates, 1992--2013") ///
    addnotes("Coefficients are treatment-year interactions relative to 1997. Unit fixed effects are included in all models. Standard errors are clustered by unit.")

copy "out/paper_figures/regression_table_annual_event_study.tex" ///
    "working/overleaf/Paper_Figures/regression_table_annual_event_study.tex", replace

* Event-study graph uses the preferred year-FE event-study estimates.
tempfile evgraph
tempname evpost
postfile `evpost' str24 measure int year double coef se lb ub using `evgraph', replace

foreach spec in best yang death {
    if "`spec'" == "best" {
        local estname ev_best_yfe
        local label "Best Track"
    }
    if "`spec'" == "yang" {
        local estname ev_yang_yfe
        local label "Mahajan-Parag grid"
    }
    if "`spec'" == "death" {
        local estname ev_death_yfe
        local label "Deaths per capita"
    }
    estimates restore `estname'
    forvalues y = 1992/2013 {
        if `y' == 1997 {
            post `evpost' ("`label'") (`y') (0) (.) (.) (.)
        }
        else {
            local b = _b[event_`y']
            local s = _se[event_`y']
            local lb = `b' - 1.96 * `s'
            local ub = `b' + 1.96 * `s'
            post `evpost' ("`label'") (`y') (`b') (`s') (`lb') (`ub')
        }
    }
}
postclose `evpost'

use `evgraph', clear
foreach m in "Best Track" "Deaths per capita" "Mahajan-Parag grid" {
    local gname = strtoname("`m'")
    twoway ///
        (rarea ub lb year if measure == "`m'", color(gs14)) ///
        (connected coef year if measure == "`m'", lcolor(black) mcolor(black) msymbol(circle) msize(vsmall)), ///
        title("`m'", size(small)) xtitle("") ytitle("") ///
        xlabel(1992(3)2013, labsize(vsmall)) ylabel(, labsize(vsmall) angle(horizontal)) ///
        yline(0, lcolor(gs8) lwidth(thin)) xline(1998, lpattern(dash) lcolor(gs8)) ///
        legend(off) graphregion(color(white)) plotregion(color(white)) name(`gname', replace)
}

twoway scatteri 0 0, msymbol(i) ///
    title("CHIRPS placeholder", size(small)) ///
    subtitle("Rainfall treatment not yet estimated", size(vsmall)) ///
    xscale(off) yscale(off) xlabel(none) ylabel(none) ///
    graphregion(color(white)) plotregion(color(white)) name(CHIRPS_placeholder, replace)

graph combine Best_Track Deaths_per_capita Mahajan_Parag_grid CHIRPS_placeholder, ///
    cols(2) iscale(.65) graphregion(color(white)) ///
    title("Annual Event-Study Estimates, Unit and Year Fixed Effects", size(medsmall)) ///
    name(eventstudy_annual_combined_4slot, replace)
graph export "out/paper_figures/eventstudy_annual_combined_4slot.png", replace width(2600)
copy "out/paper_figures/eventstudy_annual_combined_4slot.png" ///
    "working/overleaf/Paper_Figures/eventstudy_annual_combined_4slot.png", replace

* Francisco Morazan percentile among states with nonmissing deaths per capita.
import delimited using "out/data/tables/assignment/assignment_state_impacts.csv", clear varnames(1) encoding("UTF-8")
destring deaths_per_capita, replace force
keep if !missing(deaths_per_capita)
egen death_pc_rank = rank(deaths_per_capita), field
count
local n = r(N)
summarize death_pc_rank if country_name == "Honduras" & department_name == "Francisco Morazan", meanonly
local fm_rank = r(mean)
summarize deaths_per_capita if country_name == "Honduras" & department_name == "Francisco Morazan", meanonly
local fm_value = r(mean)
local fm_percentile = 100 * `fm_rank' / `n'
file open fh using "out/paper_figures/francisco_morazan_deaths_percentile.txt", write replace
file write fh "Francisco Morazan deaths_per_capita = " %9.9f (`fm_value') _n
file write fh "Ascending rank among nonmissing states = " %9.0f (`fm_rank') " of " %9.0f (`n') _n
file write fh "Weak percentile, share less than or equal = " %4.1f (`fm_percentile') _n
file close fh

log close paper
