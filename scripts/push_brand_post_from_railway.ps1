# Usage:
# Set the environment variables below or pass them as parameters.
# - $DeployUrl : base URL of your Railway service (e.g. https://your-service.up.railway.app)
# - $Token : MANUAL_RUN_TOKEN used by the service
# Example:
# $env:DEPLOY_URL = "https://your-service.up.railway.app" ; $env:MANUAL_RUN_TOKEN = "xxxx" ; pwsh .\scripts\push_brand_post_from_railway.ps1

param(
    [string]$DeployUrl = $env:DEPLOY_URL,
    [string]$Token = $env:MANUAL_RUN_TOKEN,
    [int]$WaitSeconds = 120,
    [string]$Slot = 'morning'
)

if (-not $DeployUrl) {
    Write-Error "Deploy URL not set. Set DEPLOY_URL env or pass -DeployUrl"
    exit 2
}
if (-not $Token) {
    Write-Error "MANUAL_RUN_TOKEN not set. Set MANUAL_RUN_TOKEN env or pass -Token"
    exit 2
}

$RunUrl = "$DeployUrl/run-now?slot=$Slot&token=$Token"
$HistoryUrl = "$DeployUrl/history?limit=5&token=$Token"

Write-Host "Waiting $WaitSeconds seconds before triggering run..."
Start-Sleep -Seconds $WaitSeconds

Write-Host "Triggering run: $RunUrl"
try {
    $resp = Invoke-RestMethod -Uri $RunUrl -Method Get -TimeoutSec 120
} catch {
    Write-Error "Run trigger failed: $_"
    exit 3
}

Write-Host "Run triggered. Polling history for new post..."
$retry = 0
$max = 30
$found = $false
while ($retry -lt $max -and -not $found) {
    Start-Sleep -Seconds 5
    try {
        $history = Invoke-RestMethod -Uri $HistoryUrl -Method Get -TimeoutSec 30
    } catch {
        Write-Warning "Failed to fetch history: $_"
        $retry++
        continue
    }
    if ($history -and $history.posts) {
        # Show the most recent post
        $post = $history.posts | Select-Object -First 1
        Write-Host "Latest post id: $($post.post_id)" -ForegroundColor Cyan
        Write-Host ($post | ConvertTo-Json -Depth 6)
        $found = $true
        break
    }
    $retry++
}

if (-not $found) {
    Write-Warning "No new post found in history after polling. Check service directly." 
    exit 4
}

Write-Host "Done." -ForegroundColor Green
