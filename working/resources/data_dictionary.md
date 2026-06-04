# Data Dictionary

## Track Outputs

`working/data/processed/mitch_ibtracs_track.csv`

- `SID`: IBTrACS storm identifier.
- `SEASON`: storm season.
- `BASIN`: basin code, filtered to `NA`.
- `NAME`: storm name, filtered to `MITCH`.
- `TRACK_TYPE`: IBTrACS track type, filtered to `MAIN`.
- `iso_time`: UTC timestamp.
- `lat`, `lon`: storm center in EPSG:4326.
- `wind_kt`: best available wind in knots, preferring `USA_WIND` then `WMO_WIND`.
- `pressure_mb`: best available pressure in millibars, preferring `USA_PRES` then `WMO_PRES`.
- `status`: storm status code where available.

## Distance Exposure

`working/data/processed/municipality_mitch_distance_exposure.csv`

- `muni_key`: municipality identifier.
- `country_name`, `department_name`, `municipality_name`: standardized names when available.
- `min_distance_to_track_km`: minimum projected distance from municipality geometry to the Mitch track line.
- `centroid_min_distance_to_track_km`: minimum projected distance from municipality centroid to any Mitch track point.
- `nearest_track_time`: timestamp of nearest track point to the municipality centroid.
- `nearest_track_wind_kt`: wind at the nearest track point.
- `nearest_track_pressure_mb`: pressure at the nearest track point.
- `max_track_wind_within_50km`, `max_track_wind_within_100km`, `max_track_wind_within_150km`, `max_track_wind_within_200km`: maximum track-point wind within each centroid distance threshold.

## Wind Swath Exposure

`working/data/processed/municipality_mitch_wind_swath_exposure.csv`

- `any_r34`, `any_r50`, `any_r64`: indicator equal to 1 when the municipality intersects the storm-total swath for the threshold.
- `share_area_r34`, `share_area_r50`, `share_area_r64`: share of municipality area intersecting the storm-total swath.
- `max_swath_category`: strongest intersecting swath category: `none`, `r34`, `r50`, or `r64`.

Optional continuous wind outputs:

- `max_estimated_wind_kt`: maximum modeled wind over grid cells inside the municipality.
- `mean_estimated_wind_kt`: mean modeled wind over grid cells inside the municipality.

## Rainfall Exposure

`working/data/processed/municipality_mitch_rainfall_exposure.csv`

- `mean_rainfall_mm`: mean CHIRPS rainfall value among raster cells intersecting the municipality.
- `max_rainfall_mm`: maximum CHIRPS rainfall value.
- `p90_rainfall_mm`: 90th percentile CHIRPS rainfall value.
- `rainfall_pixel_count`: number of raster cells used.
- `area_weighted_rainfall_mm`: currently the same simple raster-cell mean unless exact pixel-area weighting is added.
- `rainfall_weighting_note`: describes the weighting method.

## Merged NTL Panel

`working/data/processed/municipality_ntl_mitch_panel.csv`

- `year`: observation year.
- `satellite`: DMSP satellite or source image label.
- `stable_sum`: summed stable lights value.
- `post_1998`: 1 for years 1999 and later.
- `treated_r64`: 1 if `any_r64 == 1`.
- `treated_r50`: 1 if `any_r50 == 1`.
- `treated_r34`: 1 if `any_r34 == 1`.
- `distance_weighted_wind_kt`: fallback wind metric equal to nearest-track wind divided by `1 + centroid_min_distance_to_track_km / 50`.
- `wind_exposure_metric`: `max_estimated_wind_kt` when available, otherwise `distance_weighted_wind_kt`.
- `wind_exposure_metric_source`: source variable used for `wind_exposure_metric`.
- `rain_exposure_metric`: rainfall metric used for combined exposure, usually `mean_rainfall_mm`.
- `rain_exposure_metric_source`: source variable used for `rain_exposure_metric`.
- `high_wind`: 1 if the municipality is in the top quartile of the wind exposure metric.
- `high_rain`: 1 if the municipality is in the top quartile of the rainfall exposure metric.
- `combined_exposure_z`: z-scored wind exposure plus z-scored rainfall exposure.
