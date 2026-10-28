version 18

local ntl_cutoff 101.79
local reference_start 1996
local reference_end 1997

tempfile stata_results
tempname results
postfile `results' str12 model str32 treatment str12 panel str12 sample ///
    byte year_fe int period_start int period_end double coefficient std_error ///
    p_value ci_low ci_high long observations clusters treated_units control_units ///
    double residual_df using `stata_results', replace
global MITCH_POST_HANDLE "`results'"

capture program drop post_mitch_model
program define post_mitch_model
    version 18
    syntax, Treatment(name) Slug(string) Panel(string) Sample(string) ///
        Model(string) Yearfe(integer) Cutoff(real)

    preserve
    keep if !missing(log_ntl, muni_unit_id, year, pre_mean_stable_sum, `treatment')
    if "`sample'" == "median" {
        keep if pre_mean_stable_sum >= `cutoff'
    }

    isid muni_unit_id year
    bysort muni_unit_id: assert `treatment' == `treatment'[1]

    tempvar unit_tag
    egen byte `unit_tag' = tag(muni_unit_id)
    quietly count if `unit_tag' & `treatment' == 1
    local treated = r(N)
    quietly count if `unit_tag' & `treatment' == 0
    local controls = r(N)
    assert `treated' > 0
    assert `controls' > 0
    drop `unit_tag'

    local rhs
    local terms
    local starts
    local ends

    if "`model'" == "did" {
        generate byte post_mitch = year >= 1998
        generate double treatment_post = `treatment' * post_mitch
        local rhs treatment_post
        if !`yearfe' local rhs post_mitch treatment_post
        local terms treatment_post
        local starts 1998
        local ends 2013
    }
    else if "`model'" == "twoyear" {
        foreach period in 1992_1993 1994_1995 1998_1999 2000_2001 2002_2003 ///
            2004_2005 2006_2007 2008_2009 2010_2011 2012_2013 {
            gettoken start end : period, parse("_")
            local end = subinstr("`end'", "_", "", .)
            generate double event_`start'_`end' = `treatment' * inrange(year, `start', `end')
            local rhs `rhs' event_`start'_`end'
            local terms `terms' event_`start'_`end'
            local starts `starts' `start'
            local ends `ends' `end'
        }
    }
    else if "`model'" == "annual" {
        forvalues event_year = 1992/2013 {
            if `event_year' != 1997 {
                generate double event_`event_year' = `treatment' * (year == `event_year')
                local rhs `rhs' event_`event_year'
                local terms `terms' event_`event_year'
                local starts `starts' `event_year'
                local ends `ends' `event_year'
            }
        }
    }
    else {
        display as error "Unknown model: `model'"
        exit 198
    }

    if `yearfe' {
        quietly areg log_ntl `rhs' i.year, absorb(muni_unit_id) vce(cluster muni_unit_id)
    }
    else {
        quietly areg log_ntl `rhs', absorb(muni_unit_id) vce(cluster muni_unit_id)
    }

    local n = e(N)
    local g = e(N_clust)
    local df = e(df_r)
    local critical = invttail(`df', 0.025)

    local number_of_terms : word count `terms'
    forvalues position = 1/`number_of_terms' {
        local term : word `position' of `terms'
        local start : word `position' of `starts'
        local end : word `position' of `ends'
        local b = _b[`term']
        local se = _se[`term']
        local p = 2 * ttail(`df', abs(`b' / `se'))
        local low = `b' - `critical' * `se'
        local high = `b' + `critical' * `se'
        post $MITCH_POST_HANDLE ("`model'") ("`slug'") ("`panel'") ("`sample'") ///
            (`yearfe') (`start') (`end') (`b') (`se') (`p') (`low') (`high') ///
            (`n') (`g') (`treated') (`controls') (`df')
    }

    if "`model'" == "twoyear" {
        post $MITCH_POST_HANDLE ("`model'") ("`slug'") ("`panel'") ("`sample'") ///
            (`yearfe') (1996) (1997) (0) (.) (.) (.) (.) ///
            (`n') (`g') (`treated') (`controls') (`df')
    }
    else if "`model'" == "annual" {
        post $MITCH_POST_HANDLE ("`model'") ("`slug'") ("`panel'") ("`sample'") ///
            (`yearfe') (1997) (1997) (0) (.) (.) (.) (.) ///
            (`n') (`g') (`treated') (`controls') (`df')
    }

    restore
end

import delimited using "working/data/processed/analysis_panel_main.csv", clear varnames(1)
isid muni_unit_id year

foreach sample in all median {
    foreach year_fe in 0 1 {
        post_mitch_model, treatment(ebtrk_treat50_r64_all) slug("64kt") panel("municipal") ///
            sample("`sample'") model("twoyear") yearfe(`year_fe') cutoff(`ntl_cutoff')
        post_mitch_model, treatment(ebtrk_treat50_r50_all) slug("50kt") panel("municipal") ///
            sample("`sample'") model("twoyear") yearfe(`year_fe') cutoff(`ntl_cutoff')
        post_mitch_model, treatment(ebtrk_treat50_r34_all) slug("34kt") panel("municipal") ///
            sample("`sample'") model("twoyear") yearfe(`year_fe') cutoff(`ntl_cutoff')
        post_mitch_model, treatment(chirps_max_anomaly_top10) slug("rain_top10") panel("municipal") ///
            sample("`sample'") model("twoyear") yearfe(`year_fe') cutoff(`ntl_cutoff')
        post_mitch_model, treatment(rain50_chirps_top10) slug("wind50_rain_top10") panel("municipal") ///
            sample("`sample'") model("twoyear") yearfe(`year_fe') cutoff(`ntl_cutoff')
    }

    foreach treatment in ebtrk_treat50_r64_all ebtrk_treat50_r50_all ///
        ebtrk_treat50_r34_all chirps_max_anomaly_top10 rain50_chirps_top10 {
        if "`treatment'" == "ebtrk_treat50_r64_all" local slug "64kt"
        else if "`treatment'" == "ebtrk_treat50_r50_all" local slug "50kt"
        else if "`treatment'" == "ebtrk_treat50_r34_all" local slug "34kt"
        else if "`treatment'" == "chirps_max_anomaly_top10" local slug "rain_top10"
        else local slug "wind50_rain_top10"
        post_mitch_model, treatment(`treatment') slug("`slug'") panel("municipal") ///
            sample("`sample'") model("annual") yearfe(1) cutoff(`ntl_cutoff')
        post_mitch_model, treatment(`treatment') slug("`slug'") panel("municipal") ///
            sample("`sample'") model("did") yearfe(1) cutoff(`ntl_cutoff')
    }
}

import delimited using "working/data/processed/state_year_panel_deaths.csv", clear varnames(1)
isid muni_unit_id year

foreach sample in all median {
    foreach year_fe in 0 1 {
        post_mitch_model, treatment(death_pc_top10_state) slug("deaths_top10") panel("state") ///
            sample("`sample'") model("twoyear") yearfe(`year_fe') cutoff(`ntl_cutoff')
    }
    post_mitch_model, treatment(death_pc_top10_state) slug("deaths_top10") panel("state") ///
        sample("`sample'") model("annual") yearfe(1) cutoff(`ntl_cutoff')
    post_mitch_model, treatment(death_pc_top10_state) slug("deaths_top10") panel("state") ///
        sample("`sample'") model("did") yearfe(1) cutoff(`ntl_cutoff')
}

postclose `results'
macro drop MITCH_POST_HANDLE
use `stata_results', clear
sort model treatment panel sample year_fe period_start period_end
isid model treatment panel sample year_fe period_start period_end
export delimited using "out/results/stata/mitch_event_study_results.csv", replace
save "out/results/stata/mitch_event_study_results.dta", replace

quietly count if model == "twoyear" & treatment == "64kt" & sample == "median" ///
    & year_fe == 1 & period_start == 1998
assert r(N) == 1
quietly summarize coefficient if model == "twoyear" & treatment == "64kt" ///
    & sample == "median" & year_fe == 1 & period_start == 1998, meanonly
assert abs(r(mean) - (-0.1095531)) < 0.000001

display as result "Native Stata estimates exported."
