version 18
clear all
set more off
*******************************************************************************
* 1. Project setup
*******************************************************************************

* Run from the repository root.
local ntl_source "raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv"
local attributes "working/data/processed/municipality_attributes.csv"
local output "out/results/stata/preferred_wind_event_study.csv"
local ntl_cutoff 101.79
foreach required_file in "`ntl_source'" "`attributes'" {
    capture confirm file `required_file'
    if _rc {
        display as error "Missing required input: `required_file'"
        exit 601
    }
}

*******************************************************************************
* 2. Clean satellite-level nighttime lights
*******************************************************************************

import delimited using "`ntl_source'", clear varnames(1) case(lower) asdouble
confirm variable satellite adm0_code adm1_code adm2_code year stable_sum
assert !missing(satellite, adm0_code, adm1_code, adm2_code, year, stable_sum)
assert inrange(year, 1992, 2013)
assert stable_sum >= 0

* Administrative codes provide a stable municipality key across satellites.
generate str40 muni_key = string(adm0_code, "%12.0f") + "_" + ///
    string(adm1_code, "%12.0f") + "_" + string(adm2_code, "%12.0f")
replace muni_key = subinstr(muni_key, " ", "", .)
isid muni_key year satellite

* Average overlapping satellites so each municipality-year receives one row.
collapse (mean) stable_sum, by(muni_key year)
isid muni_key year

* Construct the sample measure from 1992-1997 only; no later outcome enters it.
bysort muni_key: egen double pre_mean_stable_sum = ///
    mean(cond(inrange(year, 1992, 1997), stable_sum, .))
assert !missing(pre_mean_stable_sum)

tempfile nightlights exposure
save `nightlights'

*******************************************************************************
* 3. Prepare and validate municipality exposure attributes
*******************************************************************************

* These documented attributes come from the repository's geospatial pipeline.
import delimited using "`attributes'", clear varnames(1) case(lower) asdouble
confirm variable muni_key in_selected_country
confirm variable ebtrk_treat50_r64_all ebtrk_treat50_r50_all
isid muni_key

foreach treatment in ebtrk_treat50_r64_all ebtrk_treat50_r50_all {
    assert inlist(`treatment', 0, 1)
}

keep muni_key in_selected_country ebtrk_treat50_r64_all ///
    ebtrk_treat50_r50_all
save `exposure'

*******************************************************************************
* 4. Merge data and construct the municipality-year panel
*******************************************************************************

use `nightlights', clear
merge m:1 muni_key using `exposure'

* Unmatched raw-light units have no audited municipality-boundary match.
quietly count if _merge == 1
assert r(N) == 1738
quietly count if _merge == 2
assert r(N) == 0
quietly count if _merge == 3
assert r(N) == 24904

keep if _merge == 3 & in_selected_country == 1
drop _merge

* Zero is a measured outcome, not a missing value; ln(1 + y) retains it.
assert stable_sum >= 0 & !missing(stable_sum)
generate double log_ntl = ln(1 + stable_sum)
egen long muni_unit_id = group(muni_key)

*******************************************************************************
* 5. Validate the panel and define the preferred sample
*******************************************************************************

confirm variable muni_unit_id year log_ntl pre_mean_stable_sum
confirm variable ebtrk_treat50_r64_all ebtrk_treat50_r50_all

* The panel must be balanced and uniquely identified before estimation.
isid muni_unit_id year
assert inrange(year, 1992, 2013)
assert !missing(muni_unit_id, year, log_ntl, pre_mean_stable_sum)
bysort muni_unit_id: assert _N == 22

quietly count
assert r(N) == 21912
quietly count if stable_sum == 0
display as text "Municipality-year zero-light observations: " r(N)

* Check rebuilt fields, then reload the versioned storage used by the paper.
rename stable_sum rebuilt_stable_sum
rename log_ntl rebuilt_log_ntl
rename pre_mean_stable_sum rebuilt_pre_mean
rename ebtrk_treat50_r64_all rebuilt_treat64
rename ebtrk_treat50_r50_all rebuilt_treat50
keep muni_key year rebuilt_*
tempfile rebuilt_checks
save `rebuilt_checks'

import delimited using "working/data/processed/analysis_panel_main.csv", ///
    clear varnames(1) case(lower) asdouble
merge 1:1 muni_key year using `rebuilt_checks', assert(3) nogen
assert abs(stable_sum - rebuilt_stable_sum) < 1e-9
assert abs(log_ntl - rebuilt_log_ntl) < 1e-12
assert abs(pre_mean_stable_sum - rebuilt_pre_mean) < 1e-9
assert ebtrk_treat50_r64_all == rebuilt_treat64
assert ebtrk_treat50_r50_all == rebuilt_treat50
import delimited using "working/data/processed/analysis_panel_main.csv", clear varnames(1)

* This restriction uses only the six pre-treatment years, 1992-1997.
keep if pre_mean_stable_sum >= `ntl_cutoff'
quietly count
assert r(N) == 10956

egen byte unit_tag = tag(muni_unit_id)
quietly count if unit_tag & ebtrk_treat50_r64_all == 1
assert r(N) == 4
quietly count if unit_tag & ebtrk_treat50_r50_all == 1
assert r(N) == 8
drop unit_tag

*******************************************************************************
* 6. Estimate the preferred two-year event studies
*******************************************************************************

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

    * The omitted 1996-1997 bin is the reference period. Municipality effects
    * are absorbed, year effects are included, and inference is clustered by
    * municipality.
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

*******************************************************************************
* 7. Export and verify machine-readable results
*******************************************************************************

postclose `results'
use `estimates', clear
sort wind period_start
isid wind period_start period_end
assert observations == 10956
assert clusters == 498
export delimited using "`output'", replace

display as result "Preferred wind event studies exported to `output'."
