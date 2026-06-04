param(
    [string]$Root = "."
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path
Set-Location $rootPath

$outAssignment = Join-Path $rootPath "out\data\tables\assignment"
$outFigures = Join-Path $rootPath "out\data\figures"
New-Item -ItemType Directory -Force -Path $outAssignment, $outFigures | Out-Null

function Get-ConstJson {
    param(
        [string]$Html,
        [string]$ConstName,
        [string]$NextConstName
    )
    $startLabel = "const $ConstName = "
    $nextLabel = "const $NextConstName"
    $start = $Html.IndexOf($startLabel)
    if ($start -lt 0) { throw "Could not find $startLabel in dashboard HTML." }
    $start += $startLabel.Length
    $next = $Html.IndexOf($nextLabel, $start)
    if ($next -lt 0) { throw "Could not find $nextLabel after $ConstName." }
    $end = $next
    while ($end -gt $start -and ($Html[$end - 1] -eq "`r" -or $Html[$end - 1] -eq "`n" -or $Html[$end - 1] -eq " " -or $Html[$end - 1] -eq ";")) {
        $end--
    }
    return $Html.Substring($start, $end - $start) | ConvertFrom-Json
}

function Clamp01([double]$x) {
    if ($x -lt 0) { return 0.0 }
    if ($x -gt 1) { return 1.0 }
    return $x
}

function NumOrNull($value) {
    if ($null -eq $value -or "$value" -eq "") { return $null }
    $out = 0.0
    if ([double]::TryParse("$value", [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$out)) {
        return $out
    }
    return $null
}

function HaversineKm([double]$lat1, [double]$lon1, [double]$lat2, [double]$lon2) {
    $toRad = [math]::PI / 180.0
    $dLat = ($lat2 - $lat1) * $toRad
    $dLon = ($lon2 - $lon1) * $toRad
    $a = [math]::Pow([math]::Sin($dLat / 2.0), 2.0) +
        [math]::Cos($lat1 * $toRad) * [math]::Cos($lat2 * $toRad) * [math]::Pow([math]::Sin($dLon / 2.0), 2.0)
    return 6371.0088 * 2.0 * [math]::Atan2([math]::Sqrt($a), [math]::Sqrt([math]::Max(0.0, 1.0 - $a)))
}

function BestDefaultScore($p) {
    $threshold = 64.0
    $radius = 150.0
    $maxWind = NumOrNull $p.max_track_wind_within_150km
    $dist = NumOrNull $p.centroid_min_distance_to_track_km
    $distanceScore = 0.0
    if ($null -ne $maxWind -and $null -ne $dist -and $maxWind -ge $threshold -and $dist -le $radius) {
        $excess = Clamp01 (($maxWind - $threshold) / [math]::Max(1.0, 155.0 - $threshold))
        $proximity = if ($radius -le 0) { 1.0 } else { Clamp01 (1.0 - $dist / $radius) }
        $distanceScore = Clamp01 ([math]::Max(0.25, $excess) * $proximity)
    }
    $swath = NumOrNull $p.share_area_r64
    if ($null -eq $swath) { $swath = 0.0 }
    return [math]::Max($distanceScore, $swath)
}

function ToBool($value) {
    $s = "$value"
    return $s.ToLowerInvariant() -eq "true" -or $s -eq "1"
}

$dashboardPath = Join-Path $rootPath "out\Mitch_integrated_dashboard.html"
$html = Get-Content $dashboardPath -Raw -Encoding UTF8
$municipalities = Get-ConstJson -Html $html -ConstName "MUNICIPALITIES" -NextConstName "STATE_IMPACTS"
$stateImpacts = Get-ConstJson -Html $html -ConstName "STATE_IMPACTS" -NextConstName "NTL_RAW"

$stateImpactRows = @()
$deathValues = @()
foreach ($s in $stateImpacts) {
    if ($s.matched_dashboard_state) {
        $dpc = NumOrNull $s.deaths_per_capita
        if ($null -ne $dpc) { $deathValues += $dpc }
    }
}
$deathMin = if ($deathValues.Count) { ($deathValues | Measure-Object -Minimum).Minimum } else { 0.0 }
$deathMax = if ($deathValues.Count) { ($deathValues | Measure-Object -Maximum).Maximum } else { 1.0 }
if ($deathMax -eq $deathMin) { $deathMax = $deathMin + 1.0 }
$stateImpactByKey = @{}
foreach ($s in $stateImpacts) {
    $dpc = NumOrNull $s.deaths_per_capita
    $hasDeath = $s.matched_dashboard_state -and $null -ne $dpc
    $score = if ($hasDeath) { Clamp01 (($dpc - $deathMin) / ($deathMax - $deathMin)) } else { 0.0 }
    $row = [pscustomobject]@{
        state_key = $s.state_key
        country_name = $s.country_name
        department_name = $s.department_name
        impact_deaths = NumOrNull $s.impact_deaths
        impact_population = NumOrNull $s.impact_population
        deaths_per_capita = $dpc
        deaths_disappearances_per_capita = NumOrNull $s.deaths_disappearances_per_capita
        death_score = $score
        has_death_data = if ($hasDeath) { 1 } else { 0 }
    }
    $stateImpactRows += $row
    $stateImpactByKey[$s.state_key] = $row
}
$stateImpactRows | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outAssignment "assignment_state_impacts.csv")

$panel = Import-Csv (Join-Path $rootPath "working\data\processed\did_dashboard\ntl_municipality_year_panel.csv")
$preValsByMuni = @{}
$preMeanByMuni = @{}
$stateYear = @{}
foreach ($r in $panel) {
    $stable = NumOrNull $r.stable_sum
    if ($null -eq $stable) { continue }
    if ([int]$r.year -le 1997) {
        if (-not $preValsByMuni.ContainsKey($r.muni_key)) { $preValsByMuni[$r.muni_key] = @() }
        $preValsByMuni[$r.muni_key] += $stable
    }
}
foreach ($k in $preValsByMuni.Keys) {
    $preMeanByMuni[$k] = ($preValsByMuni[$k] | Measure-Object -Average).Average
}

$gridPath = Join-Path $rootPath "working\data\processed\did_dashboard\yang_parag_mitch_grid.csv"
$grid = Import-Csv $gridPath | Where-Object { $_.latitude -ne "" -and $_.longitude -ne "" }
$treatedGrid = @()
$controlGrid = @()
foreach ($g in $grid) {
    $rec = [pscustomobject]@{
        grid_id = $g.grid_id
        latitude = [double]$g.latitude
        longitude = [double]$g.longitude
        cell_south = NumOrNull $g.cell_south
        cell_north = NumOrNull $g.cell_north
        cell_west = NumOrNull $g.cell_west
        cell_east = NumOrNull $g.cell_east
        country = $g.country
        is_original_treated = ToBool $g.is_original_treated
    }
    if ($rec.is_original_treated) { $treatedGrid += $rec } else { $controlGrid += $rec }
}

$selectedCountries = @("Belize", "Guatemala", "El Salvador", "Honduras", "Nicaragua")
$selectedCountrySet = @{}
foreach ($c in $selectedCountries) { $selectedCountrySet[$c] = $true }

$muniRows = @()
$muniByKey = @{}
foreach ($f in $municipalities.features) {
    $p = $f.properties
    $stateKey = "$($p.country_name)|$($p.department_name)"
    $repLat = NumOrNull $p.yang_rep_lat
    $repLon = NumOrNull $p.yang_rep_lon
    $nearestT = $null
    $nearestC = $null
    if ($null -ne $repLat -and $null -ne $repLon) {
        foreach ($g in $treatedGrid) {
            $d = HaversineKm $repLat $repLon $g.latitude $g.longitude
            if ($null -eq $nearestT -or $d -lt $nearestT) { $nearestT = $d }
        }
        foreach ($g in $controlGrid) {
            $d = HaversineKm $repLat $repLon $g.latitude $g.longitude
            if ($null -eq $nearestC -or $d -lt $nearestC) { $nearestC = $d }
        }
    }
    $yangTreated = if ($null -ne $nearestT -and ($null -eq $nearestC -or $nearestT -lt $nearestC)) { 1 } else { 0 }
    $stateImpact = $stateImpactByKey[$stateKey]
    $preMean = if ($preMeanByMuni.ContainsKey($p.muni_key)) { $preMeanByMuni[$p.muni_key] } else { $null }
    $row = [pscustomobject]@{
        muni_key = $p.muni_key
        state_key = $stateKey
        country_name = $p.country_name
        department_name = $p.department_name
        municipality_name = $p.municipality_name
        pre_mean_stable_sum = $preMean
        yang_rep_lat = $repLat
        yang_rep_lon = $repLon
        min_distance_to_track_km = NumOrNull $p.min_distance_to_track_km
        centroid_min_distance_to_track_km = NumOrNull $p.centroid_min_distance_to_track_km
        nearest_track_wind_kt = NumOrNull $p.nearest_track_wind_kt
        nearest_track_pressure_mb = NumOrNull $p.nearest_track_pressure_mb
        max_track_wind_within_50km = NumOrNull $p.max_track_wind_within_50km
        max_track_wind_within_100km = NumOrNull $p.max_track_wind_within_100km
        max_track_wind_within_150km = NumOrNull $p.max_track_wind_within_150km
        max_track_wind_within_200km = NumOrNull $p.max_track_wind_within_200km
        share_area_r34 = NumOrNull $p.share_area_r34
        any_r34 = NumOrNull $p.any_r34
        share_area_r50 = NumOrNull $p.share_area_r50
        any_r50 = NumOrNull $p.any_r50
        share_area_r64 = NumOrNull $p.share_area_r64
        any_r64 = NumOrNull $p.any_r64
        rain_total_mean_mm = NumOrNull $p.rain_total_mean_mm
        rain_total_anomaly_mm = NumOrNull $p.rain_total_anomaly_mm
        rain_max_daily_mean_mm = NumOrNull $p.rain_max_daily_mean_mm
        rain_max_daily_anomaly_mm = NumOrNull $p.rain_max_daily_anomaly_mm
        impact_deaths = if ($stateImpact) { $stateImpact.impact_deaths } else { $null }
        impact_population = if ($stateImpact) { $stateImpact.impact_population } else { $null }
        deaths_per_capita = if ($stateImpact) { $stateImpact.deaths_per_capita } else { $null }
        death_score = if ($stateImpact) { $stateImpact.death_score } else { 0.0 }
        has_death_data = if ($stateImpact) { $stateImpact.has_death_data } else { 0 }
        best_default_score = BestDefaultScore $p
        yang_nearest_treated_grid_km = $nearestT
        yang_nearest_control_grid_km = $nearestC
        yang_default_treated = $yangTreated
        in_selected_country = if ($selectedCountrySet.ContainsKey($p.country_name)) { 1 } else { 0 }
    }
    $muniRows += $row
    $muniByKey[$row.muni_key] = $row
}
$muniRows | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outAssignment "assignment_municipalities.csv")

foreach ($r in $panel) {
    if (-not $muniByKey.ContainsKey($r.muni_key)) { continue }
    $m = $muniByKey[$r.muni_key]
    if (-not $selectedCountrySet.ContainsKey($m.country_name)) { continue }
    $stable = NumOrNull $r.stable_sum
    if ($null -eq $stable) { continue }
    $key = "$($m.state_key)|$($r.year)"
    if (-not $stateYear.ContainsKey($key)) {
        $stateYear[$key] = [pscustomobject]@{
            state_key = $m.state_key
            country_name = $m.country_name
            department_name = $m.department_name
            year = [int]$r.year
            stable_sum = 0.0
        }
    }
    $stateYear[$key].stable_sum += $stable
}
$statePanel = $stateYear.Values | Sort-Object state_key, year
$statePreVals = @{}
foreach ($r in $statePanel) {
    if ($r.year -le 1997) {
        if (-not $statePreVals.ContainsKey($r.state_key)) { $statePreVals[$r.state_key] = @() }
        $statePreVals[$r.state_key] += $r.stable_sum
    }
}
$statePreMean = @{}
foreach ($k in $statePreVals.Keys) {
    $statePreMean[$k] = ($statePreVals[$k] | Measure-Object -Average).Average
}
$statePanelRows = foreach ($r in $statePanel) {
    $impact = $stateImpactByKey[$r.state_key]
    [pscustomobject]@{
        state_key = $r.state_key
        country_name = $r.country_name
        department_name = $r.department_name
        year = $r.year
        stable_sum = $r.stable_sum
        pre_mean_stable_sum = if ($statePreMean.ContainsKey($r.state_key)) { $statePreMean[$r.state_key] } else { $null }
        death_score = if ($impact) { $impact.death_score } else { 0.0 }
        has_death_data = if ($impact) { $impact.has_death_data } else { 0 }
        deaths_per_capita = if ($impact) { $impact.deaths_per_capita } else { $null }
    }
}
$statePanelRows | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outAssignment "assignment_state_year_panel.csv")

# Lightweight black-and-white map renderer for the data-section treatment maps.
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

function Flatten-FeatureRings($geometry) {
    if ($null -eq $geometry) { return }
    if ($geometry.type -eq "Polygon") {
        foreach ($ring in $geometry.coordinates) { Write-Output -NoEnumerate $ring }
    }
    elseif ($geometry.type -eq "MultiPolygon") {
        foreach ($poly in $geometry.coordinates) {
            foreach ($ring in $poly) { Write-Output -NoEnumerate $ring }
        }
    }
}

function Get-Bounds($features) {
    $minLon = 999.0; $maxLon = -999.0; $minLat = 999.0; $maxLat = -999.0
    foreach ($f in $features) {
        $rings = @()
        if ($f.geometry.type -eq "Polygon") {
            foreach ($ring in $f.geometry.coordinates) { $rings += ,$ring }
        }
        elseif ($f.geometry.type -eq "MultiPolygon") {
            foreach ($poly in $f.geometry.coordinates) {
                foreach ($ring in $poly) { $rings += ,$ring }
            }
        }
        foreach ($ring in $rings) {
            foreach ($pt in $ring) {
                $lon = [double]$pt[0]; $lat = [double]$pt[1]
                if ($lon -lt $minLon) { $minLon = $lon }
                if ($lon -gt $maxLon) { $maxLon = $lon }
                if ($lat -lt $minLat) { $minLat = $lat }
                if ($lat -gt $maxLat) { $maxLat = $lat }
            }
        }
    }
    return [pscustomobject]@{ minLon=$minLon; maxLon=$maxLon; minLat=$minLat; maxLat=$maxLat }
}

function Project-Point($lon, $lat, $bounds, $width, $height, $margin) {
    $xScale = ($width - 2 * $margin) / ($bounds.maxLon - $bounds.minLon)
    $yScale = ($height - 2 * $margin) / ($bounds.maxLat - $bounds.minLat)
    $scale = [math]::Min($xScale, $yScale)
    $mapW = ($bounds.maxLon - $bounds.minLon) * $scale
    $mapH = ($bounds.maxLat - $bounds.minLat) * $scale
    $x0 = ($width - $mapW) / 2.0
    $y0 = ($height - $mapH) / 2.0
    $x = $x0 + ($lon - $bounds.minLon) * $scale
    $y = $height - ($y0 + ($lat - $bounds.minLat) * $scale)
    return New-Object System.Drawing.PointF([float]$x, [float]$y)
}

function Feature-Path($feature, $bounds, $width, $height, $margin) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.FillMode = [System.Drawing.Drawing2D.FillMode]::Alternate
    $rings = @()
    if ($feature.geometry.type -eq "Polygon") {
        foreach ($ring in $feature.geometry.coordinates) { $rings += ,$ring }
    }
    elseif ($feature.geometry.type -eq "MultiPolygon") {
        foreach ($poly in $feature.geometry.coordinates) {
            foreach ($ring in $poly) { $rings += ,$ring }
        }
    }
    foreach ($ring in $rings) {
        $pts = New-Object System.Collections.Generic.List[System.Drawing.PointF]
        foreach ($pt in $ring) {
            $pts.Add((Project-Point ([double]$pt[0]) ([double]$pt[1]) $bounds $width $height $margin))
        }
        if ($pts.Count -ge 3) { $path.AddPolygon($pts.ToArray()) }
    }
    return $path
}

function Draw-MapImage($measure, $title, $pathOut, [switch]$DrawGrid) {
    $width = 1200
    $height = 900
    $margin = 45
    $features = @($municipalities.features | Where-Object { $selectedCountrySet.ContainsKey($_.properties.country_name) })
    $bounds = Get-Bounds $features
    $bmp = New-Object System.Drawing.Bitmap($width, $height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::White)
    $fontTitle = New-Object System.Drawing.Font("Arial", 20, [System.Drawing.FontStyle]::Bold)
    $fontLegend = New-Object System.Drawing.Font("Arial", 10)
    $blackPen = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, 0.8)
    $gridPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(150, 150, 150), 0.55)
    $treatedBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(55, 55, 55))
    $controlBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $excludedBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(238, 238, 238))
    $g.DrawString($title, $fontTitle, [System.Drawing.Brushes]::Black, 24, 18)

    foreach ($f in $features) {
        $key = $f.properties.muni_key
        $m = $muniByKey[$key]
        $preOk = $null -ne $m.pre_mean_stable_sum -and [double]$m.pre_mean_stable_sum -ge 100.0
        $included = $preOk
        $treated = $false
        if ($measure -eq "best") {
            $treated = [double]$m.best_default_score -ge 0.5
        }
        elseif ($measure -eq "yang") {
            $treated = [int]$m.yang_default_treated -eq 1
        }
        elseif ($measure -eq "death") {
            $stateImpact = $stateImpactByKey[$m.state_key]
            $statePreOk = $statePreMean.ContainsKey($m.state_key) -and [double]$statePreMean[$m.state_key] -ge 100.0
            $included = $statePreOk -and $stateImpact -and [int]$stateImpact.has_death_data -eq 1
            $treated = $stateImpact -and [double]$stateImpact.death_score -ge 0.05
        }
        $polyPath = Feature-Path $f $bounds $width $height $margin
        if (-not $included) { $g.FillPath($excludedBrush, $polyPath) }
        elseif ($treated) { $g.FillPath($treatedBrush, $polyPath) }
        else { $g.FillPath($controlBrush, $polyPath) }
        $g.DrawPath($blackPen, $polyPath)
        $polyPath.Dispose()
    }

    if ($DrawGrid) {
        foreach ($cell in $grid) {
            $countryText = "$($cell.country)"
            $show = $false
            foreach ($c in $selectedCountries) {
                if ($countryText.Contains($c)) { $show = $true; break }
            }
            if (-not $show) { continue }
            $west = NumOrNull $cell.cell_west; $east = NumOrNull $cell.cell_east
            $south = NumOrNull $cell.cell_south; $north = NumOrNull $cell.cell_north
            if ($null -eq $west -or $null -eq $east -or $null -eq $south -or $null -eq $north) { continue }
            $p1 = Project-Point $west $north $bounds $width $height $margin
            $p2 = Project-Point $east $south $bounds $width $height $margin
            $rect = New-Object System.Drawing.RectangleF([float][math]::Min($p1.X,$p2.X), [float][math]::Min($p1.Y,$p2.Y), [float][math]::Abs($p2.X-$p1.X), [float][math]::Abs($p2.Y-$p1.Y))
            $g.DrawRectangle($gridPen, $rect.X, $rect.Y, $rect.Width, $rect.Height)
        }
    }

    $legendY = $height - 64
    $g.FillRectangle($treatedBrush, 24, $legendY, 20, 14)
    $g.DrawRectangle($blackPen, 24, $legendY, 20, 14)
    $g.DrawString("Treated", $fontLegend, [System.Drawing.Brushes]::Black, 50, $legendY - 2)
    $g.FillRectangle($controlBrush, 130, $legendY, 20, 14)
    $g.DrawRectangle($blackPen, 130, $legendY, 20, 14)
    $g.DrawString("Control", $fontLegend, [System.Drawing.Brushes]::Black, 156, $legendY - 2)
    $g.FillRectangle($excludedBrush, 238, $legendY, 20, 14)
    $g.DrawRectangle($blackPen, 238, $legendY, 20, 14)
    $g.DrawString("Excluded by default NTL filter", $fontLegend, [System.Drawing.Brushes]::Black, 264, $legendY - 2)
    if ($DrawGrid) { $g.DrawString("Uniform Yang-Parag grid shown in gray", $fontLegend, [System.Drawing.Brushes]::Black, 24, $legendY + 22) }

    $bmp.Save($pathOut, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    $fontTitle.Dispose(); $fontLegend.Dispose(); $blackPen.Dispose(); $gridPen.Dispose()
    $treatedBrush.Dispose(); $controlBrush.Dispose(); $excludedBrush.Dispose()
}

$bestMap = Join-Path $outFigures "map_besttrack_default_bw.png"
$deathMap = Join-Path $outFigures "map_deaths_per_capita_default_bw.png"
$yangMap = Join-Path $outFigures "map_mahajan_parag_default_bw.png"
Draw-MapImage "best" "Best Track Reconstruction" $bestMap
Draw-MapImage "death" "Deaths per Capita" $deathMap
Draw-MapImage "yang" "Mahajan-Parag Grid" $yangMap -DrawGrid

$slotW = 1200; $slotH = 900
$combo = New-Object System.Drawing.Bitmap -ArgumentList ([int]($slotW * 2)), ([int]($slotH * 2))
$cg = [System.Drawing.Graphics]::FromImage($combo)
$cg.Clear([System.Drawing.Color]::White)
$img1 = [System.Drawing.Image]::FromFile($bestMap)
$img2 = [System.Drawing.Image]::FromFile($deathMap)
$img3 = [System.Drawing.Image]::FromFile($yangMap)
$cg.DrawImage($img1, 0, 0, $slotW, $slotH)
$cg.DrawImage($img2, $slotW, 0, $slotW, $slotH)
$cg.DrawImage($img3, 0, $slotH, $slotW, $slotH)
$blankFont = New-Object System.Drawing.Font("Arial", 26, [System.Drawing.FontStyle]::Bold)
$cg.DrawRectangle((New-Object System.Drawing.Pen([System.Drawing.Color]::Black, 1)), $slotW + 10, $slotH + 10, $slotW - 20, $slotH - 20)
$cg.DrawString("CHIRPS placeholder", $blankFont, [System.Drawing.Brushes]::Black, $slotW + 60, $slotH + 60)
$cg.DrawString("Map intentionally left blank for now", (New-Object System.Drawing.Font("Arial", 14)), [System.Drawing.Brushes]::Black, $slotW + 62, $slotH + 105)
$combo.Save((Join-Path $outFigures "map_four_treatments_default_bw.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$img1.Dispose(); $img2.Dispose(); $img3.Dispose(); $cg.Dispose(); $combo.Dispose(); $blankFont.Dispose()

Write-Host "Prepared assignment inputs and treatment maps in out/data/tables/assignment and out/data/figures."
