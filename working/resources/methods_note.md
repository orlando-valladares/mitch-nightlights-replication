# Methods Note: Mitch Wind And Rainfall Exposure

Hurricane Mitch is a difficult case for a simple wind-only treatment design. The NHC report emphasizes that the catastrophe in Honduras and Nicaragua was driven primarily by extreme rainfall, flooding, mudslides, slow storm motion, and terrain. Mitch also had a severe wind footprint near the Bay Islands and the northern Honduran coast, but that wind footprint is not the same spatial treatment as the rainfall disaster.

This pipeline therefore separates exposure into three families:

- Track-distance exposure: minimum municipality distance to the IBTrACS Mitch track and nearest-track intensity.
- Wind-radii exposure: municipality intersection with R34, R50, and R64 swaths from the CIRA/CSU Extended Best Track Dataset.
- Rainfall exposure: municipality zonal statistics from the supplied CHIRPS Mitch-duration cumulative rainfall GeoTIFF.

For wind swaths, each timestamp is represented as four quadrant sectors around the storm center using 34, 50, and 64 kt radii in nautical miles. The script converts nautical miles to kilometers, builds geodesic quadrant polygons, unions them over all Mitch timestamps, and intersects those storm-total swaths with municipality polygons. The result is a transparent categorical wind exposure approximation rather than a full meteorological reconstruction.

For 1998, the Extended Best Track radii are not official post-storm HURDAT2 best-track wind radii. The CIRA/CSU documentation states that wind radii before the early-2000s best-track era are preserved operational estimates. That makes the R34/R50/R64 treatment useful but uncertain, especially over land and in the complex terrain of Central America.

The optional continuous wind field is intentionally conservative. It is only built when radius of maximum wind is available. It linearly interpolates between Vmax at RMW and the quadrant-specific R64, R50, and R34 anchors, and leaves values outside R34 missing. If RMW is missing, the pipeline skips the continuous model rather than inventing hidden storm-structure parameters.

Recommended empirical use:

- Use rainfall and wind exposure as separate treatment channels.
- Treat `any_r64`, `any_r50`, and swath area shares as wind exposure measures.
- Treat `mean_rainfall_mm`, `p90_rainfall_mm`, and `high_rain` as flood/landslide-oriented exposure measures.
- Use `combined_exposure_z` only as a summary index after confirming the wind and rainfall layers align with the research design.
