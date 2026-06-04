clear all
set more off

capture program drop pub_summary
program define pub_summary
    syntax varlist, Saving(string)

    tempname ph
    postfile `ph' str64 variable double mean sd p10 p25 p50 p75 p90 min max n using "`saving'", replace

    foreach v of varlist `varlist' {
        quietly summarize `v', detail
        post `ph' ("`v'") (r(mean)) (r(sd)) (r(p10)) (r(p25)) (r(p50)) (r(p75)) (r(p90)) (r(min)) (r(max)) (r(N))
    }

    postclose `ph'
end

capture mkdir "out"
capture mkdir "out/data"
capture mkdir "out/data/tables"
capture mkdir "out/data/tables/publication"

capture mkdir "working/logs"
log using "working/logs/data_section_publication_stats.log", replace text

* ---------------------------------------------------------------------
* DMSP nighttime lights, raw municipality-satellite-year observations.
* ---------------------------------------------------------------------
import delimited using "raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv", clear varnames(1) case(preserve)
destring year stable_sum stable_count, replace force
pub_summary stable_sum stable_count, saving("out/data/tables/publication/ntl_raw_publication_stats.dta")
use "out/data/tables/publication/ntl_raw_publication_stats.dta", clear
export delimited using "out/data/tables/publication/ntl_raw_publication_stats.csv", replace

import delimited using "raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv", clear varnames(1) case(preserve)
destring year stable_sum stable_count, replace force
keep if year < 1999
collapse (mean) pre_mean_stable_sum=stable_sum, by(ADM0_CODE ADM1_CODE ADM2_CODE)
pub_summary pre_mean_stable_sum, saving("out/data/tables/publication/ntl_pretrend_publication_stats.dta")
use "out/data/tables/publication/ntl_pretrend_publication_stats.dta", clear
export delimited using "out/data/tables/publication/ntl_pretrend_publication_stats.csv", replace

import delimited using "raw/dmsp_satellite_municipality_year_1992_2013_ca7_sum_count.csv", clear varnames(1) case(preserve)
destring year stable_sum stable_count, replace force
preserve
    keep ADM0_NAME ADM0_CODE ADM1_CODE ADM2_CODE
    duplicates drop
    collapse (count) municipalities=ADM2_CODE, by(ADM0_NAME)
    sort ADM0_NAME
    export delimited using "out/data/tables/publication/ntl_country_coverage_publication.csv", replace
restore

* ---------------------------------------------------------------------
* IBTrACS track and municipality-level Best Track exposure.
* ---------------------------------------------------------------------
import delimited using "working/data/processed/mitch_ibtracs_track.csv", clear varnames(1) case(preserve)
destring wind_kt pressure_mb lat lon, replace force
pub_summary wind_kt pressure_mb lat lon, saving("out/data/tables/publication/besttrack_track_publication_stats.dta")
use "out/data/tables/publication/besttrack_track_publication_stats.dta", clear
export delimited using "out/data/tables/publication/besttrack_track_publication_stats.csv", replace

import delimited using "working/data/processed/did_dashboard/gaul_name_matched_exposure.csv", clear varnames(1) case(preserve)
destring min_distance_to_track_km centroid_min_distance_to_track_k nearest_track_wind_kt nearest_track_pressure_mb ///
    max_track_wind_within_50km max_track_wind_within_100km max_track_wind_within_150km max_track_wind_within_200km ///
    share_area_r34 any_r34 share_area_r50 any_r50 share_area_r64 any_r64, replace force
pub_summary min_distance_to_track_km centroid_min_distance_to_track_k nearest_track_wind_kt nearest_track_pressure_mb ///
    max_track_wind_within_50km max_track_wind_within_100km max_track_wind_within_150km max_track_wind_within_200km ///
    share_area_r34 any_r34 share_area_r50 any_r50 share_area_r64 any_r64, saving("out/data/tables/publication/besttrack_exposure_publication_stats.dta")
use "out/data/tables/publication/besttrack_exposure_publication_stats.dta", clear
export delimited using "out/data/tables/publication/besttrack_exposure_publication_stats.csv", replace

* ---------------------------------------------------------------------
* CHIRPS rainfall exposure and anomalies.
* ---------------------------------------------------------------------
import delimited using "working/data/processed/did_dashboard/gaul_name_matched_exposure.csv", clear varnames(1) case(preserve)
destring rain_total_mean_mm rain_total_max_pixel_mm rain_total_anomaly_mm rain_max_daily_mean_mm ///
    rain_max_daily_max_pixel_mm rain_max_daily_anomaly_mm rain_pixel_count, replace force
pub_summary rain_total_mean_mm rain_total_max_pixel_mm rain_total_anomaly_mm rain_max_daily_mean_mm ///
    rain_max_daily_max_pixel_mm rain_max_daily_anomaly_mm rain_pixel_count, saving("out/data/tables/publication/chirps_publication_stats.dta")
use "out/data/tables/publication/chirps_publication_stats.dta", clear
export delimited using "out/data/tables/publication/chirps_publication_stats.csv", replace

log close _all
