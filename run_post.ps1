<#
.SYNOPSIS
    Pick a product and a post type, then generate + publish it right now.

.DESCRIPTION
    Standalone, single-purpose tool. It does NOT touch scheduling. You choose:
      1) which product to post about (or let the engine auto-pick one)
      2) which kind of post to run (branding, educational, desire, trust, conversion,
         or auto)
    and it fires the exact same generate+publish pipeline the automatic schedule
    uses, right now, live.

.NOTES
    Set $env:ENGINE_BASE_URL to override the default Railway URL.
    Set $env:MANUAL_RUN_TOKEN to skip the token prompt (never echoed or logged).
#>

$BaseUrl = if ($env:ENGINE_BASE_URL) { $env:ENGINE_BASE_URL.TrimEnd("/") } else { "https://jubilant-harmony-production-5bd1.up.railway.app" }

function Get-Token {
    if ($env:MANUAL_RUN_TOKEN) { return $env:MANUAL_RUN_TOKEN }
    $secure = Read-Host "Enter MANUAL_RUN_TOKEN" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $token = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    return $token
}

# Mirrors scripts/generate_posts.py::_load_products_from_csv product_id resolution
# (SKU wins; falls back to md5(name)[:12] when SKU is blank).
function Get-ProductId {
    param([string]$Sku, [string]$Name)
    if ($Sku -and $Sku.Trim()) { return $Sku.Trim() }
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Name.ToLowerInvariant())
    $hash = $md5.ComputeHash($bytes)
    $hex = -join ($hash | ForEach-Object { $_.ToString("x2") })
    return $hex.Substring(0, 12)
}

function Get-CatalogProducts {
    $productsDir = Join-Path $PSScriptRoot "data\products"
    $csvFiles = Get-ChildItem -Path $productsDir -Filter "*.csv" -ErrorAction SilentlyContinue
    $products = @()
    foreach ($file in $csvFiles) {
        $rows = Import-Csv -Path $file.FullName
        foreach ($row in $rows) {
            if ($row.Published -ne "1") { continue }
            $name = ($row.Name | Out-String).Trim()
            if (-not $name) { continue }
            $sku = ($row.SKU | Out-String).Trim()
            $products += [pscustomobject]@{
                Name         = $name
                Sku          = $sku
                ProductId    = Get-ProductId -Sku $sku -Name $name
                RegularPrice = ($row."Regular price" | Out-String).Trim()
                SalePrice    = ($row."Sale price" | Out-String).Trim()
            }
        }
    }
    return $products | Sort-Object Name
}

$genreOptions = [ordered]@{
    "1" = @{ Label = "Branding / attention-grabbing"; Stage = "ATTENTION" }
    "2" = @{ Label = "Educational"; Stage = "EDUCATION" }
    "3" = @{ Label = "Desire / benefits & lifestyle"; Stage = "DESIRE" }
    "4" = @{ Label = "Trust / proof & credibility"; Stage = "TRUST" }
    "5" = @{ Label = "Conversion / sales push"; Stage = "CONVERSION" }
    "6" = @{ Label = "Auto (let the engine decide)"; Stage = "" }
}

function Get-CurrentSlot {
    $hour = (Get-Date).Hour
    if ($hour -lt 11) { return "morning" }
    if ($hour -lt 16) { return "midday" }
    return "evening"
}

function Invoke-EngineRunNow {
    param([string]$Token, [string]$ProductId, [string]$FunnelStage, [string]$Slot, [string]$Pipeline)
    $params = @{
        token          = $Token
        slot           = $Slot
        live           = "true"
        product_id     = $ProductId
        funnel_stage   = $FunnelStage
        pipeline       = $Pipeline
        # Manual on-demand runs should always go out on every channel and
        # never be silently skipped by the automatic schedule's stage-per-slot
        # rules or the scheduled-cadence duplicate window.
        platforms      = "facebook,instagram,linkedin"
        duplicate_mode = "allow_all"
    }
    $pairs = @()
    foreach ($key in $params.Keys) {
        $value = [string]$params[$key]
        if ($value -ne "") { $pairs += "$key=$([System.Uri]::EscapeDataString($value))" }
    }
    $url = "$BaseUrl/run-now?" + ($pairs -join "&")
    return Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop
}

function Wait-ForRunToFinish {
    param([string]$Token)
    Write-Host "`nWaiting for the run to finish..." -ForegroundColor DarkGray
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        try {
            $status = Invoke-RestMethod -Uri "$BaseUrl/status" -Method Get -ErrorAction Stop
        } catch {
            continue
        }
        if ($status.last_run.status -ne "running") {
            return $true
        }
    }
    return $false
}

Write-Host "=== Run a post now ===" -ForegroundColor Cyan
Write-Host "Loading product catalog from data\products\*.csv ..." -ForegroundColor DarkGray
$catalog = Get-CatalogProducts
if (-not $catalog -or $catalog.Count -eq 0) {
    Write-Host "No products found under data\products. Aborting." -ForegroundColor Red
    return
}

Write-Host "`nPick a product:" -ForegroundColor Cyan
Write-Host "  0) Auto - let the engine choose the product"
for ($i = 0; $i -lt $catalog.Count; $i++) {
    $p = $catalog[$i]
    $price = if ($p.SalePrice) { "$($p.SalePrice) (was $($p.RegularPrice))" } else { $p.RegularPrice }
    Write-Host ("{0,3}) {1}  [{2}]  {3}" -f ($i + 1), $p.Name, $p.ProductId, $price)
}
$productChoice = Read-Host "`nProduct number"
$productId = ""
$productLabel = "Auto"
if ($productChoice -and $productChoice -ne "0") {
    $idx = 0
    if ([int]::TryParse($productChoice, [ref]$idx) -and $idx -ge 1 -and $idx -le $catalog.Count) {
        $selected = $catalog[$idx - 1]
        $productId = $selected.ProductId
        $productLabel = $selected.Name
    } else {
        Write-Host "Invalid selection, defaulting to Auto." -ForegroundColor Yellow
    }
}

Write-Host "`nPick a post type:" -ForegroundColor Cyan
foreach ($key in $genreOptions.Keys) {
    Write-Host ("  {0}) {1}" -f $key, $genreOptions[$key].Label)
}
$genreChoice = Read-Host "`nPost type number"
$genre = $genreOptions["6"]
if ($genreOptions.Contains($genreChoice)) { $genre = $genreOptions[$genreChoice] }

$pipelineOptions = [ordered]@{
    "1" = @{ Label = "Auto (env default / ENABLE_SOCIAL_INTELLIGENCE)"; Value = "" }
    "2" = @{ Label = "Legacy pipeline (generate_posts + social_visuals)"; Value = "legacy" }
    "3" = @{ Label = "Social Intelligence Orchestrator"; Value = "orchestrator" }
    "4" = @{ Label = "Best of both (run both, keep the higher-scoring post)"; Value = "best_of" }
}
Write-Host "`nPick a content pipeline:" -ForegroundColor Cyan
foreach ($key in $pipelineOptions.Keys) {
    Write-Host ("  {0}) {1}" -f $key, $pipelineOptions[$key].Label)
}
$pipelineChoice = Read-Host "`nPipeline number"
$pipeline = $pipelineOptions["1"]
if ($pipelineOptions.Contains($pipelineChoice)) { $pipeline = $pipelineOptions[$pipelineChoice] }

$slot = Get-CurrentSlot
Write-Host "`nAbout to publish LIVE on Facebook, Instagram, and LinkedIn:" -ForegroundColor Yellow
Write-Host "  Product:   $productLabel"
Write-Host "  Post type: $($genre.Label)"
Write-Host "  Pipeline:  $($pipeline.Label)"
Write-Host "  Slot:      $slot"
$confirm = Read-Host "`nPublish this now? [y/N]"
if ($confirm -notmatch "^(y|yes)$") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    return
}

$token = Get-Token
try {
    $result = Invoke-EngineRunNow -Token $token -ProductId $productId -FunnelStage $genre.Stage -Slot $slot -Pipeline $pipeline.Value
} catch {
    Write-Host "Failed to start the run: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message -ForegroundColor Yellow }
    return
}

if (-not $result.accepted) {
    Write-Host "Engine did not accept the run (a run may already be in progress). Response:" -ForegroundColor Red
    $result | ConvertTo-Json -Depth 8 | Write-Host
    return
}

Write-Host "Run started." -ForegroundColor Green
if (Wait-ForRunToFinish -Token $token) {
    $history = Invoke-RestMethod -Uri "$BaseUrl/history?limit=1" -Method Get -ErrorAction Stop
    Write-Host "`nLatest post record:" -ForegroundColor Cyan
    $history.posts | ConvertTo-Json -Depth 10 | Write-Host
} else {
    Write-Host "Still running after 3 minutes; check /history yourself when ready." -ForegroundColor Yellow
}
