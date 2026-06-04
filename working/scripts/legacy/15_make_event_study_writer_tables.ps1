param(
    [string]$Root = ".",
    [string]$OutDirName = "writer_event_tables"
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path
Set-Location $rootPath

$outDir = Join-Path $rootPath "out\tables\$OutDirName"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Escape-Rtf($value) {
    if ($null -eq $value) { return "" }
    $s = [string]$value
    $s = $s -replace "\\", "\\"
    $s = $s -replace "\{", "\{"
    $s = $s -replace "\}", "\}"
    return $s
}

function NumOrNull($value) {
    if ($null -eq $value -or "$value" -eq "") { return $null }
    $n = 0.0
    if ([double]::TryParse("$value", [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$n)) {
        return $n
    }
    return $null
}

function Stars($p) {
    $pn = NumOrNull $p
    if ($null -eq $pn) { return "" }
    if ($pn -lt 0.01) { return "***" }
    if ($pn -lt 0.05) { return "**" }
    if ($pn -lt 0.10) { return "*" }
    return ""
}

function CoefText($row) {
    if ($row.reference -eq "1") { return "0.000" }
    $b = NumOrNull $row.coef
    if ($null -eq $b) { return "" }
    return $b.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture) + (Stars $row.p)
}

function SeText($row) {
    if ($row.reference -eq "1") { return "(ref.)" }
    $se = NumOrNull $row.se
    if ($null -eq $se) { return "" }
    return "(" + $se.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture) + ")"
}

function PeriodLabel($row) {
    if ($row.period_start -eq $row.period_end) { return "$($row.period_start)" }
    return "$($row.period_start)-$($row.period_end)"
}

function Build-EventSection($title, $subtitle, $rows) {
    $measures = @("Best Track", "Mahajan-Parag grid", "Deaths per capita")
    $periods = $rows | Sort-Object {[int]$_.period_start}, measure | Group-Object period_start,period_end | Sort-Object { [int](($_.Name -split ", ")[0]) }

    $cellDefs = "\cellx1800\cellx4800\cellx7800\cellx10800"
    $section = "\pard\qc\b\fs24 $(Escape-Rtf $title)\b0\fs18\par`r`n"
    $section += "\pard\qc\i $(Escape-Rtf $subtitle)\i0\par`r`n"
    $section += "\pard\par`r`n"
    $section += "\trowd\trgaph80\trleft0$cellDefs`r`n"
    $section += "\intbl\b Period\b0\cell \intbl\b Best Track\b0\cell \intbl\b Mahajan-Parag\b0\cell \intbl\b Deaths per capita\b0\cell \row`r`n"

    foreach ($p in $periods) {
        $first = $p.Group | Select-Object -First 1
        $shade = if ($first.highlight -eq "1") { "\clcbpat1" } else { "" }
        $label = PeriodLabel $first
        $byMeasure = @{}
        foreach ($m in $measures) {
            $byMeasure[$m] = $p.Group | Where-Object { $_.measure -eq $m } | Select-Object -First 1
        }

        $section += "\trowd\trgaph80\trleft0$shade\cellx1800$shade\cellx4800$shade\cellx7800$shade\cellx10800`r`n"
        $section += "\intbl $(Escape-Rtf $label)\cell "
        foreach ($m in $measures) { $section += "\intbl $(Escape-Rtf (CoefText $byMeasure[$m]))\cell " }
        $section += "\row`r`n"

        $section += "\trowd\trgaph80\trleft0$shade\cellx1800$shade\cellx4800$shade\cellx7800$shade\cellx10800`r`n"
        $section += "\intbl \cell "
        foreach ($m in $measures) { $section += "\intbl $(Escape-Rtf (SeText $byMeasure[$m]))\cell " }
        $section += "\row`r`n"
    }

    $section += "\pard\fs16 Notes: Each cell reports an event-study difference-in-differences coefficient, with clustered standard errors in parentheses. The omitted reference period is shown as 0.000 with '(ref.)' beneath it. Unit and period fixed effects are included. Shaded rows overlap 1998-2002. * p<0.10, ** p<0.05, *** p<0.01.\par`r`n"
    return $section
}

function Write-Rtf($path, $sections) {
    $rtf = "{\rtf1\ansi\deff0{\fonttbl{\f0 Times New Roman;}}{\colortbl ;\red235\green235\blue235;}\paperw12240\paperh15840\margl720\margr720\margt720\margb720\f0\fs18`r`n"
    $rtf += ($sections -join "\page`r`n")
    $rtf += "}"
    Set-Content -Path $path -Value $rtf -Encoding ASCII
}

$rows = Import-Csv "out\results\event_study_results_long.csv"

$annual = @($rows | Where-Object { $_.grouping -eq "annual" })
$twoYear = @($rows | Where-Object { $_.grouping -eq "two_year" })
$fourYear = @($rows | Where-Object { $_.grouping -eq "four_year" })

$annualSection = Build-EventSection `
    "Annual Event-Study Difference-in-Differences Estimates" `
    "Outcome: log(1 + DMSP-OLS stable lights). Reference year: 1997." `
    $annual

$twoYearSection = Build-EventSection `
    "Two-Year Binned Event-Study Difference-in-Differences Estimates" `
    "Outcome: log(1 + DMSP-OLS stable lights). Reference bin: 1996-1997." `
    $twoYear

$fourYearSection = Build-EventSection `
    "Four-Year Binned Event-Study Difference-in-Differences Estimates" `
    "Outcome: log(1 + DMSP-OLS stable lights). Reference bin: 1996-1997; four-year post bins preserve a clean pre-Mitch reference." `
    $fourYear

Write-Rtf (Join-Path $outDir "event_study_annual_writer.rtf") @($annualSection)
Write-Rtf (Join-Path $outDir "event_study_two_year_writer.rtf") @($twoYearSection)
Write-Rtf (Join-Path $outDir "event_study_four_year_writer.rtf") @($fourYearSection)
Write-Rtf (Join-Path $outDir "event_study_all_tables_writer.rtf") @($annualSection, $twoYearSection, $fourYearSection)

Write-Host "Event-study Writer tables created in $outDir"
