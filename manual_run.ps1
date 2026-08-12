<#
.SYNOPSIS
    Interactive manual control panel for the infenergy-social-engine Railway service.

.DESCRIPTION
    Wraps the worker.py HTTP endpoints (status, history, run-now, run-marketing,
    run-weekly, inventory-sync, agents, delete-post, etc.) behind a menu so you
    don't have to hand-build query strings and tokens every time.

.NOTES
    Set $env:ENGINE_BASE_URL to override the default Railway URL.
    Set $env:MANUAL_RUN_TOKEN to skip the token prompt (it is never echoed or logged).
#>

$script:BaseUrl = if ($env:ENGINE_BASE_URL) { $env:ENGINE_BASE_URL.TrimEnd("/") } else { "https://jubilant-harmony-production-5bd1.up.railway.app" }
$script:Token = $env:MANUAL_RUN_TOKEN

function Get-EngineToken {
    if (-not $script:Token) {
        $secure = Read-Host "Enter MANUAL_RUN_TOKEN" -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $script:Token = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    return $script:Token
}

function Invoke-Engine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [hashtable]$QueryParams = @{},
        [switch]$NeedsAuth
    )
    if ($NeedsAuth) {
        $QueryParams["token"] = Get-EngineToken
    }
    $pairs = @()
    foreach ($key in $QueryParams.Keys) {
        $value = [string]$QueryParams[$key]
        if ($value -ne "") {
            $pairs += "$key=$([System.Uri]::EscapeDataString($value))"
        }
    }
    $url = "$script:BaseUrl$Path"
    if ($pairs.Count -gt 0) {
        $url += "?" + ($pairs -join "&")
    }
    Write-Host "GET $url" -ForegroundColor DarkGray
    try {
        $response = Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop
        Write-Host ($response | ConvertTo-Json -Depth 12)
        return $response
    } catch {
        Write-Host "Request failed: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.ErrorDetails.Message) {
            Write-Host $_.ErrorDetails.Message -ForegroundColor Yellow
        }
        return $null
    }
}

function Confirm-Action {
    param([string]$Message)
    $answer = Read-Host "$Message [y/N]"
    return $answer -match "^(y|yes)$"
}

function Read-WithDefault {
    param([string]$Prompt, [string]$Default = "")
    $label = if ($Default) { "$Prompt (default: $Default)" } else { $Prompt }
    $value = Read-Host $label
    if (-not $value) { return $Default }
    return $value
}

function Show-Status {
    Invoke-Engine -Path "/status" | Out-Null
}

function Show-History {
    $limit = Read-WithDefault -Prompt "How many posts" -Default "10"
    Invoke-Engine -Path "/history" -QueryParams @{ limit = $limit } | Out-Null
}

function Show-QualityReport {
    $limit = Read-WithDefault -Prompt "Sample size" -Default "50"
    Invoke-Engine -Path "/quality-report" -QueryParams @{ limit = $limit } -NeedsAuth | Out-Null
}

function Show-Campaign {
    Invoke-Engine -Path "/campaign-current" -NeedsAuth | Out-Null
}

function Show-InventorySnapshot {
    Invoke-Engine -Path "/inventory-db" -NeedsAuth | Out-Null
}

function Invoke-InventorySync {
    $force = Confirm-Action "Force full reseed from CSV even if unchanged?"
    Invoke-Engine -Path "/inventory-sync" -QueryParams @{ force = $force.ToString().ToLower() } -NeedsAuth | Out-Null
}

function Show-AgentsList {
    Invoke-Engine -Path "/agents/list" | Out-Null
}

function Invoke-AgentRun {
    $name = Read-WithDefault -Prompt "Agent name (see Agents List)"
    if (-not $name) { Write-Host "Agent name is required." -ForegroundColor Yellow; return }
    Invoke-Engine -Path "/agents/run" -QueryParams @{ name = $name } -NeedsAuth | Out-Null
}

function Invoke-RunMarketingTeam {
    if (Confirm-Action "Run the marketing team pipeline now?") {
        Invoke-Engine -Path "/run-marketing" -NeedsAuth | Out-Null
    }
}

function Invoke-RunWeekly {
    if (Confirm-Action "Run the weekly planner + campaign build now?") {
        Invoke-Engine -Path "/run-weekly" -NeedsAuth | Out-Null
    }
}

function Invoke-RunNow {
    $slot = Read-WithDefault -Prompt "Slot (morning/midday/evening)" -Default "morning"
    $liveAnswer = Confirm-Action "Publish LIVE (not dry-run)?"
    $live = if ($liveAnswer) { "true" } else { "false" }
    $platforms = Read-WithDefault -Prompt "Platforms (comma-separated, blank = default)" -Default ""
    $productId = Read-WithDefault -Prompt "Force a specific product_id (blank = auto)" -Default ""
    $funnelStage = Read-WithDefault -Prompt "Force funnel_stage (ATTENTION/EDUCATION/TRUST/DESIRE/CONVERSION, blank = auto)" -Default ""
    $pipeline = Read-WithDefault -Prompt "pipeline (legacy/orchestrator/best_of, blank = env default)" -Default ""
    $duplicateMode = Read-WithDefault -Prompt "duplicate_mode (strict/exact_only/allow_all, blank = env default)" -Default ""
    $readinessBlock = Read-WithDefault -Prompt "readiness_block override (true/false, blank = env default)" -Default ""

    if ($live -eq "true" -and -not (Confirm-Action "This will publish a REAL live post. Continue?")) {
        Write-Host "Cancelled." -ForegroundColor Yellow
        return
    }

    $params = @{
        slot            = $slot
        live            = $live
        platforms       = $platforms
        product_id      = $productId
        funnel_stage    = $funnelStage
        pipeline        = $pipeline
        duplicate_mode  = $duplicateMode
        readiness_block = $readinessBlock
    }
    $result = Invoke-Engine -Path "/run-now" -QueryParams $params -NeedsAuth
    if ($result -and $result.accepted -and (Confirm-Action "Watch /status until this run finishes?")) {
        Watch-RunCompletion
    }
}

function Watch-RunCompletion {
    Write-Host "Polling /status every 5s (up to 3 minutes)..." -ForegroundColor DarkGray
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        try {
            $status = Invoke-RestMethod -Uri "$script:BaseUrl/status" -Method Get -ErrorAction Stop
        } catch {
            continue
        }
        Write-Host "last_run.status = $($status.last_run.status)" -ForegroundColor DarkGray
        if ($status.last_run.status -ne "running") {
            Write-Host "Run finished. Latest history entry:" -ForegroundColor Green
            Invoke-Engine -Path "/history" -QueryParams @{ limit = 1 } | Out-Null
            return
        }
    }
    Write-Host "Timed out waiting; check /history manually." -ForegroundColor Yellow
}

function Invoke-DeletePost {
    $platform = Read-WithDefault -Prompt "Platform (facebook/instagram/linkedin)"
    $postId = Read-WithDefault -Prompt "post_id"
    if (-not $platform -or -not $postId) { Write-Host "Both platform and post_id are required." -ForegroundColor Yellow; return }
    if (-not (Confirm-Action "This permanently deletes a live post ($platform/$postId). Continue?")) {
        Write-Host "Cancelled." -ForegroundColor Yellow
        return
    }
    Invoke-Engine -Path "/delete-post" -QueryParams @{ platform = $platform; post_id = $postId } -NeedsAuth | Out-Null
}

function Invoke-BrandProfileApply {
    if (Confirm-Action "Re-apply the founder brand manifesto to the live brand profile?") {
        Invoke-Engine -Path "/brand-profile-apply" -NeedsAuth | Out-Null
    }
}

function Invoke-SellingIdeologyApply {
    if (Confirm-Action "Re-apply the selling ideology payload?") {
        Invoke-Engine -Path "/selling-ideology-apply" -NeedsAuth | Out-Null
    }
}

function Invoke-RawRequest {
    $path = Read-WithDefault -Prompt "Path (e.g. /run-now)"
    if (-not $path.StartsWith("/")) { $path = "/$path" }
    $rawParams = Read-WithDefault -Prompt "Query params as key=value pairs, comma-separated (blank = none)" -Default ""
    $needsAuth = Confirm-Action "Does this endpoint require the token?"
    $params = @{}
    if ($rawParams) {
        foreach ($pair in $rawParams.Split(",")) {
            $kv = $pair.Split("=", 2)
            if ($kv.Count -eq 2) { $params[$kv[0].Trim()] = $kv[1].Trim() }
        }
    }
    if ($needsAuth) {
        Invoke-Engine -Path $path -QueryParams $params -NeedsAuth | Out-Null
    } else {
        Invoke-Engine -Path $path -QueryParams $params | Out-Null
    }
}

function Show-Menu {
    Write-Host ""
    Write-Host "=== infenergy-social-engine manual control panel ===" -ForegroundColor Cyan
    Write-Host "Target: $script:BaseUrl"
    Write-Host " 1) Status"
    Write-Host " 2) History"
    Write-Host " 3) Quality report"
    Write-Host " 4) Current campaign"
    Write-Host " 5) Inventory snapshot"
    Write-Host " 6) Inventory sync (force reseed option)"
    Write-Host " 7) List agents"
    Write-Host " 8) Run an agent"
    Write-Host " 9) Run marketing team pipeline"
    Write-Host "10) Run weekly planner"
    Write-Host "11) Run now (publish a post)"
    Write-Host "12) Delete a live post"
    Write-Host "13) Re-apply brand profile"
    Write-Host "14) Re-apply selling ideology"
    Write-Host "15) Raw request (any endpoint)"
    Write-Host " 0) Exit"
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Choose an option"
    switch ($choice) {
        "1"  { Show-Status }
        "2"  { Show-History }
        "3"  { Show-QualityReport }
        "4"  { Show-Campaign }
        "5"  { Show-InventorySnapshot }
        "6"  { Invoke-InventorySync }
        "7"  { Show-AgentsList }
        "8"  { Invoke-AgentRun }
        "9"  { Invoke-RunMarketingTeam }
        "10" { Invoke-RunWeekly }
        "11" { Invoke-RunNow }
        "12" { Invoke-DeletePost }
        "13" { Invoke-BrandProfileApply }
        "14" { Invoke-SellingIdeologyApply }
        "15" { Invoke-RawRequest }
        "0"  { break }
        default { Write-Host "Unknown option." -ForegroundColor Yellow }
    }
    if ($choice -eq "0") { break }
}
