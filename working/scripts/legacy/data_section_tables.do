version 18
clear all
set more off

* Run from the project root.

capture mkdir "out"
capture mkdir "out/data"
capture mkdir "out/data/tables"
capture mkdir "out/data/tables/stata"

program define write_summary
    syntax varlist using/
    tempname handle
    postfile `handle' str80 variable double mean sd min max n using "`using'", replace
    foreach v of varlist `varlist' {
        quietly summarize `v'
        post `handle' ("`v'") (r(mean)) (r(sd)) (r(min)) (r(max)) (r(N))
    }
    postclose `handle'
end

program define write_tabcount
    syntax varname using/
    preserve
        contract `varlist'
        rename _freq n
        export delimited using "`using'", replace
    restore
end

* ---------------------------------------------------------------------
* DMSP NTL raw panel: all available municipality-satellite-year rows.
* ---------------------------------------------------------------------
import delimited using "raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv", clear varnames(1) case(preserve)

egen muni_key = concat(ADM0_CODE ADM1_CODE ADM2_CODE), punct("_")
destring year stable_sum stable_count ADM0_CODE ADM1_CODE ADM2_CODE, replace force

write_summary stable_sum stable_count year using "out/data/tables/stata/stata_ntl_summary.dta"
use "out/data/tables/stata/stata_ntl_summary.dta", clear
export delimited using "out/data/tables/stata/stata_ntl_summary.csv", replace

import delimited using "raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv", clear varnames(1) case(preserve)
egen muni_key = concat(ADM0_CODE ADM1_CODE ADM2_CODE), punct("_")
destring year stable_sum stable_count ADM0_CODE ADM1_CODE ADM2_CODE, replace force
preserve
    keep if year <= 1998
    collapse (mean) pre_mean_stable_sum=stable_sum, by(muni_key ADM0_NAME ADM1_NAME ADM2_NAME)
    write_summary pre_mean_stable_sum using "out/data/tables/stata/stata_ntl_pretrend_summary.dta"
    use "out/data/tables/stata/stata_ntl_pretrend_summary.dta", clear
    export delimited using "out/data/tables/stata/stata_ntl_pretrend_summary.csv", replace
restore

preserve
    contract ADM0_NAME
    rename _freq ntl_rows
    export delimited using "out/data/tables/stata/stata_ntl_rows_by_country.csv", replace
restore

preserve
    keep ADM0_NAME muni_key
    duplicates drop
    contract ADM0_NAME
    rename _freq municipalities
    export delimited using "out/data/tables/stata/stata_ntl_municipalities_by_country.csv", replace
restore

* ---------------------------------------------------------------------
* IBTrACS/Best Track and municipality wind exposure.
* ---------------------------------------------------------------------
import delimited using "working/data/processed/mitch_ibtracs_track.csv", clear varnames(1) case(preserve)
destring lat lon wind_kt pressure_mb, replace force
write_summary wind_kt pressure_mb lat lon using "out/data/tables/stata/stata_besttrack_track_summary.dta"
use "out/data/tables/stata/stata_besttrack_track_summary.dta", clear
export delimited using "out/data/tables/stata/stata_besttrack_track_summary.csv", replace

import delimited using "working/data/processed/did_dashboard/gaul_name_matched_exposure.csv", clear varnames(1) case(preserve)
destring min_distance_to_track_km centroid_min_distance_to_track_k nearest_track_wind_kt nearest_track_pressure_mb ///
    max_track_wind_within_50km max_track_wind_within_100km max_track_wind_within_150km max_track_wind_within_200km ///
    share_area_r34 any_r34 share_area_r50 any_r50 share_area_r64 any_r64, replace force
write_summary min_distance_to_track_km centroid_min_distance_to_track_k nearest_track_wind_kt nearest_track_pressure_mb ///
    max_track_wind_within_50km max_track_wind_within_100km max_track_wind_within_150km max_track_wind_within_200km ///
    share_area_r34 any_r34 share_area_r50 any_r50 share_area_r64 any_r64 using "out/data/tables/stata/stata_besttrack_exposure_summary.dta"
use "out/data/tables/stata/stata_besttrack_exposure_summary.dta", clear
export delimited using "out/data/tables/stata/stata_besttrack_exposure_summary.csv", replace

* ---------------------------------------------------------------------
* CHIRPS rainfall exposure and anomalies.
* ---------------------------------------------------------------------
import delimited using "working/data/processed/did_dashboard/gaul_name_matched_exposure.csv", clear varnames(1) case(preserve)
destring rain_total_mean_mm rain_total_max_pixel_mm rain_total_anomaly_mm rain_max_daily_mean_mm ///
    rain_max_daily_max_pixel_mm rain_max_daily_anomaly_mm rain_pixel_count, replace force
write_summary rain_total_mean_mm rain_total_max_pixel_mm rain_total_anomaly_mm rain_max_daily_mean_mm ///
    rain_max_daily_max_pixel_mm rain_max_daily_anomaly_mm rain_pixel_count using "out/data/tables/stata/stata_chirps_summary.dta"
use "out/data/tables/stata/stata_chirps_summary.dta", clear
export delimited using "out/data/tables/stata/stata_chirps_summary.csv", replace

* ---------------------------------------------------------------------
* GAUL-matched dashboard coverage and default NTL threshold counts.
* ---------------------------------------------------------------------
import delimited using "working/data/processed/did_dashboard/ntl_municipality_year_panel.csv", clear varnames(1) case(preserve)
destring year stable_sum pre_mean_stable_sum, replace force
preserve
    keep muni_key pre_mean_stable_sum
    duplicates drop
    generate pre_mean_ge_700 = pre_mean_stable_sum >= 700 if !missing(pre_mean_stable_sum)
    contract pre_mean_ge_700
    rename _freq municipalities
    export delimited using "out/data/tables/stata/stata_ntl_pre700_counts.csv", replace
restore

log close _all
