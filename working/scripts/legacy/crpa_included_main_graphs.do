version 18
clear all
set more off

* Run from the project root. This writes a comparison set that includes
* Costa Rica and Panama as controls; it does not overwrite the main paper outputs.
cd "Z:/home/orlando-valladares/Trabajo/ECON64"

capture log close withcrpa
capture mkdir "working/logs"
log using "working/logs/crpa_included_main_graphs.log", replace name(withcrpa) text

capture mkdir "out"
capture mkdir "out/results"
capture mkdir "out/results/with_crpa"
capture mkdir "out/results/with_crpa/figures"
capture mkdir "out/results/with_crpa/tables"

adopath ++ "working/ado"
graph set window fontface "Arial"
set scheme s2mono

* ---------------------------------------------------------------------
* Build municipality and department panels without dropping CR/PA.
* ---------------------------------------------------------------------
import delimited using "out/data/tables/assignment/assignment_municipalities.csv", clear varnames(1) encoding("UTF-8")
destring pre_mean_stable_sum best_default_score yang_default_treated death_score has_death_data ///
    deaths_per_capita, replace force
gen byte include_default = !missing(pre_mean_stable_sum) & pre_mean_stable_sum >= 100
tempfile muni
save `muni', replace

preserve
    keep state_key country_name department_name death_score has_death_data deaths_per_capita
    duplicates drop
    bysort state_key: keep if _n == 1
    tempfile state_meta
    save `state_meta', replace
restore

import delimited using "working/data/processed/did_dashboard/ntl_municipality_year_panel.csv", clear varnames(1) encoding("UTF-8")
destring year stable_sum pre_mean_stable_sum, replace force
merge m:1 muni_key using `muni', keep(match) nogen
keep if inrange(year, 1992, 2013)
gen log_ntl = ln(stable_sum + 1)
egen muni_unit_id = group(muni_key)
tempfile muni_panel
save `muni_panel', replace

preserve
    collapse (sum) stable_sum, by(state_key year)
    merge m:1 state_key using `state_meta', keep(match) nogen
    gen pre_stable_tmp = stable_sum if year <= 1998
    egen pre_mean_stable_sum = mean(pre_stable_tmp), by(state_key)
    drop pre_stable_tmp
    gen log_ntl = ln(stable_sum + 1)
    gen byte death_include_default = !missing(pre_mean_stable_sum) & pre_mean_stable_sum >= 100 & has_death_data == 1
    egen state_unit_id = group(state_key)
    tempfile state_panel
    save `state_panel', replace
restore

* ---------------------------------------------------------------------
* Annual DiD regression records for the CR/PA-included comparison.
* ---------------------------------------------------------------------
capture program drop collect_reg
program define collect_reg
    syntax, Measure(string) Treatvar(name) Unitvar(name) Timevar(name) Yearfe(integer)

    tempvar post treat_post
    gen byte `post' = `timevar' >= 1998
    gen double `treat_post' = `treatvar' * `post'
    quietly levelsof `unitvar' if `treatvar' == 1, local(tunits)
    quietly levelsof `unitvar' if `treatvar' == 0, local(cunits)
    local nt : word count `tunits'
    local nc : word count `cunits'

    if `yearfe' == 1 {
        quietly areg log_ntl `treat_post' i.`timevar', absorb(`unitvar') vce(cluster `unitvar')
    }
    else {
        quietly areg log_ntl `post' `treat_post', absorb(`unitvar') vce(cluster `unitvar')
    }
    local b = _b[`treat_post']
    local se = _se[`treat_post']
    local p = 2 * ttail(e(df_r), abs(`b' / `se'))
    post DIDPOST ("`measure'") (`yearfe') (`b') (`se') (`p') (e(N)) (e(r2)) (`nt') (`nc')
    drop `post' `treat_post'
end

tempname DIDPOST
postfile DIDPOST str32 measure byte year_fe double coef se p n r2 treated_units control_units ///
    using "out/results/with_crpa/tables/did_results_annual.dta", replace

use `muni_panel', clear
keep if include_default
gen byte treat_best = best_default_score >= .5
gen byte treat_yang = yang_default_treated == 1
collect_reg, measure("Best Track") treatvar(treat_best) unitvar(muni_unit_id) timevar(year) yearfe(0)
collect_reg, measure("Best Track") treatvar(treat_best) unitvar(muni_unit_id) timevar(year) yearfe(1)
collect_reg, measure("Mahajan-Parag grid") treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) yearfe(0)
collect_reg, measure("Mahajan-Parag grid") treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) yearfe(1)

use `state_panel', clear
keep if death_include_default
gen byte treat_death = death_score >= .05
collect_reg, measure("Deaths per capita") treatvar(treat_death) unitvar(state_unit_id) timevar(year) yearfe(0)
collect_reg, measure("Deaths per capita") treatvar(treat_death) unitvar(state_unit_id) timevar(year) yearfe(1)
postclose DIDPOST

use "out/results/with_crpa/tables/did_results_annual.dta", clear
export delimited using "out/results/with_crpa/tables/did_results_annual.csv", replace

* ---------------------------------------------------------------------
* Annual event-study estimates with unit and year fixed effects.
* ---------------------------------------------------------------------
capture program drop collect_event
program define collect_event
    syntax, Measure(string) Treatvar(name) Unitvar(name) Timevar(name) Base(integer)

    tempvar treated
    gen byte `treated' = `treatvar'
    quietly levelsof `unitvar' if `treated' == 1, local(tunits)
    quietly levelsof `unitvar' if `treated' == 0, local(cunits)
    local nt : word count `tunits'
    local nc : word count `cunits'

    quietly levelsof `timevar', local(periods)
    local evvars
    local i = 0
    foreach per of local periods {
        local ++i
        tempvar ev`i'
        gen double `ev`i'' = `treated' * (`timevar' == `per')
        local period`i' = `per'
        local evname`i' "`ev`i''"
        if `per' != `base' {
            local evvars `evvars' `ev`i''
        }
    }

    quietly areg log_ntl i.`timevar' `evvars', absorb(`unitvar') vce(cluster `unitvar')
    local nobs = e(N)
    local r2val = e(r2)

    forvalues j = 1/`i' {
        local per = `period`j''
        local highlight = (`per' >= 1998 & `per' <= 2002)
        if `per' == `base' {
            post EVENTPOST ("`measure'") (`per') (`base') (1) (0) (.) (.) (`nobs') (`r2val') (`nt') (`nc') (`highlight')
        }
        else {
            local evvar "`evname`j''"
            local b = _b[`evvar']
            local se = _se[`evvar']
            local p = 2 * ttail(e(df_r), abs(`b' / `se'))
            post EVENTPOST ("`measure'") (`per') (`base') (0) (`b') (`se') (`p') (`nobs') (`r2val') (`nt') (`nc') (`highlight')
        }
    }
    drop `treated'
end

tempname EVENTPOST
postfile EVENTPOST str32 measure int year base_period byte reference double coef se p n r2 ///
    treated_units control_units byte highlight ///
    using "out/results/with_crpa/tables/event_study_results_annual.dta", replace

use `muni_panel', clear
keep if include_default
gen byte treat_best = best_default_score >= .5
gen byte treat_yang = yang_default_treated == 1
collect_event, measure("Best Track") treatvar(treat_best) unitvar(muni_unit_id) timevar(year) base(1997)
collect_event, measure("Mahajan-Parag grid") treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) base(1997)

use `state_panel', clear
keep if death_include_default
gen byte treat_death = death_score >= .05
collect_event, measure("Deaths per capita") treatvar(treat_death) unitvar(state_unit_id) timevar(year) base(1997)
postclose EVENTPOST

use "out/results/with_crpa/tables/event_study_results_annual.dta", clear
export delimited using "out/results/with_crpa/tables/event_study_results_annual.csv", replace

* ---------------------------------------------------------------------
* DiD visual-comparison panels.
* ---------------------------------------------------------------------
capture program drop did_graph_current
program define did_graph_current
    syntax, Treatvar(name) Unitvar(name) Timevar(name) Panellabel(string) Outstub(string) Xstep(integer)

    tempvar unitmean adjusted
    egen `unitmean' = mean(log_ntl), by(`unitvar')
    quietly summarize log_ntl, meanonly
    gen double `adjusted' = log_ntl - `unitmean' + r(mean)
    collapse (mean) mean_log=`adjusted', by(`timevar' `treatvar')
    reshape wide mean_log, i(`timevar') j(`treatvar')
    sort `timevar'
    quietly summarize `timevar' if `timevar' < 1998, meanonly
    local ref = r(max)
    quietly summarize mean_log1 if `timevar' == `ref', meanonly
    local tbase = r(mean)
    quietly summarize mean_log0 if `timevar' == `ref', meanonly
    local cbase = r(mean)
    gen double treated_cf = .
    replace treated_cf = `tbase' + (mean_log0 - `cbase') if `timevar' >= 1998

    twoway ///
        (line mean_log1 `timevar', lcolor(black) lpattern(solid) lwidth(medthick)) ///
        (line mean_log0 `timevar', lcolor(gs7) lpattern(dash) lwidth(medthick)) ///
        (line treated_cf `timevar', lcolor(black) lpattern(shortdash) lwidth(medthick)), ///
        title("`panellabel'", size(small)) ///
        xtitle("") ytitle("Mean log(1 + stable lights)", size(small)) ///
        xlabel(1992(`xstep')2013, labsize(small)) ylabel(, angle(horizontal) labsize(small)) ///
        xline(1998, lpattern(dash) lcolor(gs9) lwidth(thin)) ///
        xline(1999, lpattern(shortdash) lcolor(gs6) lwidth(thin)) ///
        xline(2002, lpattern(dot) lcolor(gs10) lwidth(thin)) ///
        legend(order(1 "Treated" 2 "Control" 3 "Treated counterfactual") rows(1) size(vsmall) region(lstyle(none))) ///
        graphregion(color(white)) plotregion(color(white)) name(`outstub', replace)
    graph export "out/results/with_crpa/figures/`outstub'.png", replace width(2200)
end

use `muni_panel', clear
keep if include_default
gen byte treat_best = best_default_score >= .5
did_graph_current, treatvar(treat_best) unitvar(muni_unit_id) timevar(year) ///
    panellabel("Best Track") outstub(did_annual_besttrack) xstep(3)

use `state_panel', clear
keep if death_include_default
gen byte treat_death = death_score >= .05
did_graph_current, treatvar(treat_death) unitvar(state_unit_id) timevar(year) ///
    panellabel("Deaths per Capita") outstub(did_annual_deaths_per_capita) xstep(3)

use `muni_panel', clear
keep if include_default
gen byte treat_yang = yang_default_treated == 1
did_graph_current, treatvar(treat_yang) unitvar(muni_unit_id) timevar(year) ///
    panellabel("Mahajan-Parag Grid") outstub(did_annual_mahajan_parag) xstep(3)

* ---------------------------------------------------------------------
* Event-study graph panels.
* ---------------------------------------------------------------------
import delimited using "out/results/with_crpa/tables/event_study_results_annual.csv", clear varnames(1) encoding("UTF-8")
gen lb = coef - 1.96 * se
gen ub = coef + 1.96 * se
replace lb = . if reference == 1
replace ub = . if reference == 1

foreach m in "Best Track" "Deaths per capita" "Mahajan-Parag grid" {
    local gname = strtoname("`m'")
    local stub = lower("`gname'")
    twoway ///
        (rarea ub lb year if measure == "`m'", color(gs14)) ///
        (connected coef year if measure == "`m'", lcolor(black) mcolor(black) msymbol(circle) msize(vsmall)), ///
        title("`m'", size(small)) xtitle("") ytitle("") ///
        xlabel(1992(3)2013, labsize(vsmall)) ylabel(, labsize(vsmall) angle(horizontal)) ///
        yline(0, lcolor(gs8) lwidth(thin)) xline(1998, lpattern(dash) lcolor(gs8)) ///
        legend(off) graphregion(color(white)) plotregion(color(white)) name(`gname', replace)
    graph export "out/results/with_crpa/figures/eventstudy_annual_`stub'.png", replace width(1400)
}

display as text "CR/PA-included comparison outputs written to out/results/with_crpa."
log close withcrpa
