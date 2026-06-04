# Bottles Stata Runbook

Use the Bottles Stata install when native `stata`, `stata-se`, or `stata-mp`
are unavailable in the Linux shell.

## Bottle Details

- Bottle name: `Stata`
- Bottles Flatpak app: `com.usebottles.bottles`
- Registered program: `StataSE-64`
- Windows Stata executable inside the bottle:
  `C:\Program Files\Stata18\StataSE-64.exe`

## Batch Wrapper Pattern

Run project scripts from the project root through Wine's `Z:` drive mapping.

Example:

```stata
version 18
clear all
set more off

cd "Z:/home/orlando-valladares/Trabajo/ECON64"
do "make.do"
```

Run it from the Linux terminal with the project path exposed to Flatpak:

```bash
flatpak run --filesystem=/home/orlando-valladares/Trabajo/ECON64 \
  --command=bottles-cli com.usebottles.bottles \
  run -b Stata -p StataSE-64 --args-replace \
  /e do Z:/home/orlando-valladares/Trabajo/ECON64/make.do
```

The `--filesystem=...` flag matters. Without it, Stata may launch but fail to
find files under `Z:/home/...`.

## esttab / estout

The bottle may fail on `ssc install estout` because Stata's temporary directory
inside Wine can reject the installer copy step. For reproducible project runs,
keep SSC `estout` files in `working/ado/` and add this near the top of the
Stata script:

```stata
adopath ++ "working/ado"
```

Then `which esttab` should resolve from the project-local ado folder.

## Useful Checks

List registered programs:

```bash
flatpak run --command=bottles-cli com.usebottles.bottles programs -b Stata
```

If a Stata batch run cannot find the script, check the batch log under:

```text
/home/orlando-valladares/.var/app/com.usebottles.bottles/data/bottles/bottles/Stata/drive_c/Program Files/Stata18/
```

If a Wine/Stata graph command hangs, stop it with:

```bash
pkill -f StataSE-64.exe
```
