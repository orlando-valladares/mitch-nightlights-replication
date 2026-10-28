# Municipality Boundary Correction Changes

Generated: 2026-05-31 22:51 EDT

## What disappeared and where

The missing municipalities disappeared at the GAUL/NTL-to-GeoBoundaries geometry join used to build `working/data/processed/did_dashboard/municipality_boundaries.geojson`. The source NTL rows were still present, but the map and any downstream geometry-dependent extraction could not draw or spatially extract them because the previous join required exact normalized ADM1/ADM2 names. Accent differences, department aliases, spelling variants, and renamed municipalities therefore failed before final boundary output.

The correction keeps the policy conservative: exact matches are accepted automatically; audited aliases are accepted only when one NTL unit maps to exactly one GeoBoundaries polygon and that polygon is not claimed by another NTL unit. Ambiguous, placeholder, lake, island-fragment, and unresolved named units remain unmatched rather than being forced.

## Corrected coverage

- All CA7 NTL municipalities: 1,211
- Matched after audited aliases: 1,132
- Audited alias matches: 84
- Still unmatched after aliases: 79

Selected-country coverage:

| Country | Matched | Unmatched |
|---|---:|---:|
| Belize | 6 | 0 |
| El Salvador | 241 | 21 |
| Guatemala | 331 | 5 |
| Honduras | 288 | 3 |
| Nicaragua | 130 | 28 |

## Key audited fixes

- Honduras, El Paraiso: 18 municipalities now match through the ADM1 alias `Paraiso` -> `El Paraiso`; all are audited 1:1 matches.
- Nicaragua: 41 audited alias matches restore the formerly missing eastern/devolved-department cases and spelling/name variants, including Atlantico Norte/Sur, Matagalpa, Jinotega, Nueva Segovia, and related ADM2 aliases.
- Guatemala: 15 audited alias matches restore spelling/accent/name variants such as Raxruha, La Tinta, Quezaltepeque, San Raimundo, Palopo variants, and related municipal names.

## Still non-1:1

- 27: No conservative 1:1 polygon match found in GeoBoundaries after audited aliases.
- 19: Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries.
- 6: No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon.
- 2: Water body / lake unit in the NTL source; GeoBoundaries municipality polygons do not contain a 1:1 lake municipality.
- 2: Alias is not accepted because multiple NTL units would map to the same polygon.
- 1: Alias is not accepted because it does not point to exactly one GeoBoundaries polygon.

Important examples that remain unmatched:
- Nicaragua: Atlantico Norte / Sunbeam; Atlantico Sur / Great Corn Island; Atlantico Sur / Isla; Atlantico Sur / Little Corn Island; Chinandega / Isla Mangles Altos; Chinandega / Tonala; Chontales / Isla El Muerto; Chontales / Isla Grade; Chontales / Isla Redonda; Chontales / Islas El Nancital; Chontales / Administrative unit not available; Granada / Isla Las Calabazas; plus 16 more.
- Guatemala: Guatemala / Lago de Amatitlán; Sololá / Lago de Atitlán; Suchitepéquez / Pueblo Nuevo; Suchitepéquez / Río Bravo; Izabal / Administrative unit not available.
- Honduras: Francisco Morazan / Santa  Ana; Francisco Morazan / Santa Ana; Name Unknown / Name Unknown.
- El Salvador: Chalatenango / San Ignacio; Chalatenango / Chalatenango; Chalatenango / Cancasque; Chalatenango / San Antonio Los Ranchos; Usulutan / San Buena Ventura; Chalatenango / Las Flores; La Paz / San Francisco Chinameca; La Paz / San Emigdio; La Paz / Jerusalen; Cabanas / Ilobasco; Cabanas / Tejutepeque; Cabanas / Guacotecti; plus 9 more.

## NTL and CHIRPS after correction

Once a unit is matched 1:1, its DMSP-OLS NTL data are already available from the existing municipality-year extract and the corrected panel rebuilds directly from it. CHIRPS is also accessible because the corrected polygon is passed through the raster extraction step; any all-NaN CHIRPS warnings reflect raster windows with no valid pixels, not missing municipality names. Units that remain non-1:1 do not receive forced NTL geometry joins or CHIRPS polygon extraction because that would silently invent a boundary.

## Files produced

- `working/municipality_boundary_match_registry.csv`: row-level audited registry.
- `working/municipality_boundary_match_registry.md`: human-readable registry summary and unmatched list.
- `working/data/processed/did_dashboard/gaul_boundary_match_registry.csv`: processed dashboard registry copy.
- `working/data/processed/did_dashboard/municipality_boundaries.geojson`: corrected matched geometry output.
- `working/data/processed/analysis_panel_main.csv`: rebuilt corrected analysis panel.
