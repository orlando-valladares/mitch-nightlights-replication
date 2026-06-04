# AGENTS.md

## Scope
These instructions apply to the whole repository unless a deeper AGENTS.md overrides them.

## Folder rules
- Never modify, move, rename, or delete files inside `raw/`.
- Treat `raw/` as read-only source data.
- Save all working data, intermediate files, downloaded resources, and logs in `working/`.
- Save final outputs, results, figures, dashboards, tables, and writeups in `out/`.


## Project structure
- `raw/` contains immutable source inputs only: DMSP-OLS municipality-year extracts, Mitch impact source tables, CHIRPS rasters, GeoBoundaries files, IBTrACS/EBTRK files, and other external raw resources. Do not write outputs here.
- `working/` contains reproducible pipeline code, processed/intermediate datasets, logs, registries, and the Overleaf working copy. Important subfolders include:
  - `working/scripts/source_prep/`: source preparation scripts for downloads, storm tracks, wind swaths, CHIRPS extraction, NTL merges, and GAUL/GeoBoundaries matching.
  - `working/scripts/build_01_municipality_attributes.py`: builds municipality-level treatment/exposure attributes.
  - `working/scripts/build_02_municipality_year_panel.py`: builds the DMSP-OLS municipality-year outcome panel.
  - `working/scripts/build_03_analysis_panel.py`: merges attributes and outcomes into the main analysis panel.
  - `working/scripts/build_04_regressions.py`: builds regression-ready results.
  - `working/scripts/build_05_tables_figures.py`: builds final tables, figures, maps, and structured Overleaf assets.
  - `working/scripts/pipeline_engine.py`: shared Python engine for treatment construction, summary tables, figures, regression tables, and structured outputs.
  - `working/data/processed/`: canonical processed data created from `raw/`, including matched municipality boundaries, exposure tables, and analysis panels.
  - `working/logs/`: Stata and pipeline logs.
  - `working/overleaf/`: editable LaTeX project and generated paper assets.
  - `working/municipality_boundary_match_registry.*`: audited registry of GAUL-to-GeoBoundaries 1:1 matches and unresolved non-1:1 units.
- `out/` contains final outputs for review and submission: dashboards, figures, paper tables, result tables, structured replication outputs, and exported writeups.
- Top-level `make.do` calls `analyze.do` and `graph.do`; those Stata drivers dispatch the staged Python scripts above. Prefer changing the staged scripts or `pipeline_engine.py` rather than hand-editing generated outputs.

## Logging
- Keep one cumulative, condensed work-session log at `working/work_sessions.md`.
- Append a new entry to `working/work_sessions.md` at the end of every work session.
- Each entry should briefly record: date/time, objective, files touched, key commands run, outputs created, and unresolved issues.
- Do not create separate per-session Markdown log files unless explicitly requested.

## Stata workflow
- Prefer reproducible `.do` files over ad hoc command sequences.
- The project should generally have:
  - `make.do` = builds the whole project.
  - `analyze.do` = handles specific analyses, figures, or components.
- If creating a new analysis section, prefer adding or updating an `analyze.do`-style file rather than putting everything into one script.
- Use relative paths only.
- Preserve existing comments and add short comments for new sections.

## Data handling
- Do not silently change variable definitions, sample restrictions, merges, or units.
- If a judgment call is required, state it explicitly in the session log.
- Keep data lineage clear: `raw/` → `working/` → `out/`.

## Outputs
- Do not overwrite important final outputs unless explicitly asked.
- Label figures and tables clearly with titles, axes, units, and source notes when applicable.
- When results change, state exactly which result changed and why.

## Destructive actions
- Ask before deleting files, renaming folders, changing schemas, or overwriting existing outputs.

## Communication style
- Be concise.
- State assumptions clearly.
- Flag uncertainty rather than guessing.
