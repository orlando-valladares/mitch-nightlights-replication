param(
    [string]$Root = ".",
    [string]$OutDirName = "writer"
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

function Format-Cell($value) {
    if ($null -eq $value) { return "" }
    $s = ([string]$value).Trim()
    if ($s -eq "") { return "" }
    $num = 0.0
    if ([double]::TryParse($s, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$num)) {
        if ([math]::Abs($num - [math]::Round($num)) -lt 0.0000001) {
            return $num.ToString("N0", [Globalization.CultureInfo]::InvariantCulture)
        }
        if ([math]::Abs($num) -ge 100) { return $num.ToString("0.0", [Globalization.CultureInfo]::InvariantCulture) }
        if ([math]::Abs($num) -ge 10) { return $num.ToString("0.00", [Globalization.CultureInfo]::InvariantCulture) }
        if ([math]::Abs($num) -ge 1) { return $num.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture) }
        if ($num -ne 0) { return $num.ToString("0.0000", [Globalization.CultureInfo]::InvariantCulture) }
        return "0"
    }
    return $s
}

function Get-RtfTable($title, $subtitle, $rows, $columns, $labels) {
    $totalWidth = 14400
    $cellWidth = [math]::Floor($totalWidth / $columns.Count)
    $cellDefs = ""
    for ($i = 1; $i -le $columns.Count; $i++) {
        $cellDefs += "\cellx$($i * $cellWidth)"
    }

    $rtf = "\pard\b\fs26 $(Escape-Rtf $title)\b0\fs18\par`r`n"
    if ($subtitle -ne "") { $rtf += "\pard\i $(Escape-Rtf $subtitle)\i0\par`r`n" }
    $rtf += "\pard\par`r`n"

    $rtf += "\trowd\trgaph60\trleft0$cellDefs`r`n"
    foreach ($col in $columns) {
        $label = if ($labels.ContainsKey($col)) { $labels[$col] } else { $col }
        $rtf += "\intbl\b $(Escape-Rtf $label)\b0\cell "
    }
    $rtf += "\row`r`n"

    foreach ($row in $rows) {
        $rtf += "\trowd\trgaph60\trleft0$cellDefs`r`n"
        foreach ($col in $columns) {
            $rtf += "\intbl $(Escape-Rtf (Format-Cell $row.$col))\cell "
        }
        $rtf += "\row`r`n"
    }
    $rtf += "\pard\par`r`n"
    return $rtf
}

function Write-RtfDocument($path, $sections) {
    $body = "{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\paperw15840\paperh12240\landscape\margl720\margr720\margt720\margb720\f0\fs16`r`n"
    $body += ($sections -join "\page`r`n")
    $body += "}"
    Set-Content -Path $path -Value $body -Encoding ASCII
}

$ntl = Import-Csv "out\tables\assignment\ntl_summary_crpa_excluded.csv"
$treatment = Import-Csv "out\tables\assignment\treatment_summary_crpa_excluded.csv"
$storm = Import-Csv "out\tables\assignment\storm_track_wind_pressure_summary.csv"
$reg = Import-Csv "out\results\regression_results_long.csv"

$ntlLabels = @{
    panel = "Panel"; item = "Item"; definition = "Definition"; mean = "Mean"; sd = "SD";
    p10 = "P10"; p25 = "P25"; p50 = "P50"; p75 = "P75"; p90 = "P90";
    min = "Min"; max = "Max"; n = "N"; source = "Source"
}
$treatmentLabels = @{
    panel = "Panel"; measure = "Measure"; unit = "Unit"; included_units = "Included units";
    treated_units = "Treated units"; control_units = "Control units";
    treated_municipalities = "Treated municipalities"; control_municipalities = "Control municipalities";
    mean_score = "Mean score"; sd_score = "SD score"; assumptions = "Assumptions"
}
$stormLabels = @{
    variable = "Variable"; mean = "Mean"; sd = "SD"; p10 = "P10"; p25 = "P25";
    p50 = "P50"; p75 = "P75"; p90 = "P90"; n = "N"; source = "Source"
}
$regLabels = @{
    grouping = "Grouping"; measure = "Measure"; year_fe = "Year FE"; coef = "Coef.";
    se = "SE"; p = "p-value"; n = "N"; r2 = "R-squared";
    treated_units = "Treated units"; control_units = "Control units"
}

$ntlSection = Get-RtfTable `
    "DMSP-OLS Nighttime Lights Summary Statistics" `
    "Costa Rica and Panama excluded." `
    $ntl `
    @("panel","item","definition","mean","sd","p10","p25","p50","p75","p90","min","max","n","source") `
    $ntlLabels

$treatmentSection = Get-RtfTable `
    "Treatment Summary Statistics" `
    "Default dashboard setup and no-nighttime-lights-filter comparison." `
    $treatment `
    @("panel","measure","unit","included_units","treated_units","control_units","treated_municipalities","control_municipalities","mean_score","sd_score","assumptions") `
    $treatmentLabels

$stormSection = Get-RtfTable `
    "Storm Track Wind and Pressure Summary" `
    "Storm-center wind speed and pressure only; latitude and longitude omitted." `
    $storm `
    @("variable","mean","sd","p10","p25","p50","p75","p90","n","source") `
    $stormLabels

$annualSection = Get-RtfTable `
    "Annual Difference-in-Differences Estimates" `
    "Outcome: log(1 + DMSP-OLS stable lights). Standard errors clustered by unit." `
    @($reg | Where-Object { $_.grouping -eq "annual" }) `
    @("measure","year_fe","coef","se","p","n","r2","treated_units","control_units") `
    $regLabels

$twoYearSection = Get-RtfTable `
    "Two-Year Grouped Difference-in-Differences Estimates" `
    "Outcome: log(1 + DMSP-OLS stable lights). Standard errors clustered by unit." `
    @($reg | Where-Object { $_.grouping -eq "two_year" }) `
    @("measure","year_fe","coef","se","p","n","r2","treated_units","control_units") `
    $regLabels

$fourYearSection = Get-RtfTable `
    "Four-Year Grouped Difference-in-Differences Estimates" `
    "Outcome: log(1 + DMSP-OLS stable lights). Standard errors clustered by unit." `
    @($reg | Where-Object { $_.grouping -eq "four_year" }) `
    @("measure","year_fe","coef","se","p","n","r2","treated_units","control_units") `
    $regLabels

Write-RtfDocument (Join-Path $outDir "dmsp_ols_summary_statistics_writer.rtf") @($ntlSection)
Write-RtfDocument (Join-Path $outDir "treatment_summary_statistics_writer.rtf") @($treatmentSection)
Write-RtfDocument (Join-Path $outDir "storm_track_summary_statistics_writer.rtf") @($stormSection)
Write-RtfDocument (Join-Path $outDir "regression_table_annual_writer.rtf") @($annualSection)
Write-RtfDocument (Join-Path $outDir "regression_table_two_year_writer.rtf") @($twoYearSection)
Write-RtfDocument (Join-Path $outDir "regression_table_four_year_writer.rtf") @($fourYearSection)
Write-RtfDocument (Join-Path $outDir "all_recent_tables_for_libreoffice_writer.rtf") @(
    $ntlSection,
    $treatmentSection,
    $stormSection,
    $annualSection,
    $twoYearSection,
    $fourYearSection
)

Copy-Item "out\results\regression_table_annual.rtf" (Join-Path $outDir "original_regression_table_annual.rtf") -Force
Copy-Item "out\results\regression_table_two_year.rtf" (Join-Path $outDir "original_regression_table_two_year.rtf") -Force
Copy-Item "out\results\regression_table_four_year.rtf" (Join-Path $outDir "original_regression_table_four_year.rtf") -Force

Write-Host "Writer-ready tables created in $outDir"
