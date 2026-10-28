version 18
clear all
set more off

*******************************************************************************
* 1. File locations
*******************************************************************************

local ntl_source "data/raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv"
local attributes "data/processed/municipality_attributes.csv"
local stata_panel "data/processed/stata_analysis_panel_main.dta"

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

generate str40 muni_key = string(adm0_code, "%12.0f") + "_" + ///
    string(adm1_code, "%12.0f") + "_" + string(adm2_code, "%12.0f")
replace muni_key = subinstr(muni_key, " ", "", .)
isid muni_key year satellite

* Some years have two satellites. Their municipality sums receive equal weight.
collapse (mean) stable_sum, by(muni_key year)
isid muni_key year
assert stable_sum >= 0

* The preferred sample rule is based only on the six pre-Mitch years.
bysort muni_key: egen double pre_mean_stable_sum = ///
    mean(cond(inrange(year, 1992, 1997), stable_sum, .))
assert !missing(pre_mean_stable_sum)

tempfile nightlights exposure
save `nightlights'

*******************************************************************************
* 3. Prepare documented municipality exposure attributes
*******************************************************************************

import delimited using "`attributes'", clear varnames(1) case(lower) asdouble
confirm variable muni_key in_selected_country
confirm variable ebtrk_treat50_r64_all ebtrk_treat50_r50_all
confirm variable ebtrk_treat50_r34_all chirps_max_anomaly_top10
isid muni_key

foreach treatment in ebtrk_treat50_r64_all ebtrk_treat50_r50_all ///
    ebtrk_treat50_r34_all chirps_max_anomaly_top10 ///
    death_pc_top10_state rain50_chirps_top10 {
    assert inlist(`treatment', 0, 1)
}

keep muni_key in_selected_country chirps_max_anomaly_top10 ///
    death_pc_top10_state rain50_chirps_top10 ebtrk_share_r64_all ///
    ebtrk_share_r50_all ebtrk_share_r34_all ebtrk_treat50_r64_all ///
    ebtrk_treat50_r50_all ebtrk_treat50_r34_all
save `exposure'

*******************************************************************************
* 4. Merge outcomes and exposure, then construct the analysis panel
*******************************************************************************

use `nightlights', clear
merge m:1 muni_key using `exposure'

* Seventy-nine raw-light units lack an audited boundary match and are excluded.
quietly count if _merge == 1
assert r(N) == 1738
quietly count if _merge == 2
assert r(N) == 0
quietly count if _merge == 3
assert r(N) == 24904
keep if _merge == 3 & in_selected_country == 1
drop _merge

generate double log_ntl = ln(1 + stable_sum)
egen long muni_unit_id = group(muni_key)
order muni_key year stable_sum log_ntl in_selected_country ///
    pre_mean_stable_sum, first

isid muni_unit_id year
assert !missing(muni_unit_id, year, stable_sum, log_ntl, pre_mean_stable_sum)
assert inrange(year, 1992, 2013)
bysort muni_unit_id: assert _N == 22
bysort muni_unit_id: assert pre_mean_stable_sum == pre_mean_stable_sum[1]

quietly count
assert r(N) == 21912
quietly count if stable_sum == 0
display as text "Municipality-year zero-light observations: " r(N)
quietly count if pre_mean_stable_sum >= 101.79
assert r(N) == 10956
display as text "Preferred-sample municipality-years: " r(N)

*******************************************************************************
* 5. Verify the rebuilt fields against the packaged analysis panel
*******************************************************************************

tempfile rebuilt_panel
save `rebuilt_panel'

capture confirm file "data/processed/analysis_panel_main.csv"
if !_rc {
    import delimited using "data/processed/analysis_panel_main.csv", ///
        clear varnames(1) case(lower) asdouble
    keep muni_key year stable_sum log_ntl pre_mean_stable_sum ///
        ebtrk_treat50_r64_all ebtrk_treat50_r50_all ebtrk_treat50_r34_all
    rename stable_sum canonical_stable_sum
    rename log_ntl canonical_log_ntl
    rename pre_mean_stable_sum canonical_pre_mean
    rename ebtrk_treat50_r64_all canonical_treat64
    rename ebtrk_treat50_r50_all canonical_treat50
    rename ebtrk_treat50_r34_all canonical_treat34

    merge 1:1 muni_key year using `rebuilt_panel', assert(3) nogen
    assert abs(stable_sum - canonical_stable_sum) < 1e-9
    assert abs(log_ntl - canonical_log_ntl) < 1e-12
    assert abs(pre_mean_stable_sum - canonical_pre_mean) < 1e-9
    assert ebtrk_treat50_r64_all == canonical_treat64
    assert ebtrk_treat50_r50_all == canonical_treat50
    assert ebtrk_treat50_r34_all == canonical_treat34
    display as result "Rebuilt panel agrees with the packaged analysis fields."
}

use `rebuilt_panel', clear
compress
save "`stata_panel'", replace
display as result "Stata analysis panel saved to `stata_panel'."
