# Data Dictionary: Stata Showcase

| Variable | Level | Definition |
|---|---|---|
| `muni_unit_id` | Unit | Numeric panel identifier; municipality in the main panel and state in the mortality panel |
| `muni_key` | Municipality | Stable project key formed during boundary matching |
| `year` | Unit-year | Calendar year, 1992–2013 |
| `stable_sum` | Municipality-year | DMSP-OLS stable-light sum averaged across available satellites within municipality-year |
| `log_ntl` | Municipality-year | `ln(1 + stable_sum)` |
| `pre_mean_stable_sum` | Unit | Mean stable-light sum during 1992–1997 |
| `ebtrk_treat50_r64_all` | Municipality | One if at least 50% of area is inside the storm-total 64-knot EBTRK swath |
| `ebtrk_treat50_r50_all` | Municipality | One if at least 50% of area is inside the storm-total 50-knot EBTRK swath |
| `ebtrk_treat50_r34_all` | Municipality | One if at least 50% of area is inside the storm-total 34-knot EBTRK swath |
| `chirps_max_anomaly_top10` | Municipality | One for the top decile of maximum Mitch-period CHIRPS rainfall anomaly |
| `rain50_chirps_top10` | Municipality | Combined 50-knot and top-decile rainfall indicator used in supporting output |
| `death_pc_top10_state` | State | One for states in the top decile of compiled deaths per capita |

The preferred sample is `pre_mean_stable_sum >= 101.79`. The omitted two-year event-study period is 1996–1997. The annual robustness specification omits 1997.
