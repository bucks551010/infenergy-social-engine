param(
    [switch]$SkipValidation,
    [string]$StateFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Mask-Token {
    param([string]$Token)
    if (-not $Token) { return "" }
    if ($Token.Length -le 12) { return "********" }
    return ($Token.Substring(0, 6) + "..." + $Token.Substring($Token.Length - 6))
}

function Required-Env {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "User")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    }
    if (-not $value -or -not $value.Trim()) {
        throw "Missing required environment variable: $Name"
    }
    return $value.Trim()
}

function Save-UserEnv {
    param(
        [string]$Name,
        [string]$Value
    )
    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    Set-Item -Path ("Env:" + $Name) -Value $Value
}

function Invoke-GraphGet {
    param([string]$Url)
    try {
        return Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 45
    }
    catch {
        $msg = $_.Exception.Message
        throw "Graph call failed: $msg`nURL: $Url"
    }
}

$graphVersion = "v20.0"
$graphBase = "https://graph.facebook.com/$graphVersion"

$appId = Required-Env -Name "META_APP_ID"
$appSecret = Required-Env -Name "META_APP_SECRET"
$pageId = Required-Env -Name "META_PAGE_ID"
$currentLongUser = Required-Env -Name "META_LONG_LIVED_USER_TOKEN"

$exchangeUrl = "$graphBase/oauth/access_token?grant_type=fb_exchange_token&client_id=$([uri]::EscapeDataString($appId))&client_secret=$([uri]::EscapeDataString($appSecret))&fb_exchange_token=$([uri]::EscapeDataString($currentLongUser))"
$exchange = Invoke-GraphGet -Url $exchangeUrl
$newLongUser = [string]$exchange.access_token
$expiresIn = [int]$exchange.expires_in

if (-not $newLongUser) {
    throw "Meta did not return a refreshed long-lived token."
}

if (-not $SkipValidation) {
    $appToken = "$appId|$appSecret"
    $debugUrl = "$graphBase/debug_token?input_token=$([uri]::EscapeDataString($newLongUser))&access_token=$([uri]::EscapeDataString($appToken))"
    $debug = Invoke-GraphGet -Url $debugUrl
    if (-not $debug.data.is_valid) {
        throw "Refreshed token failed validation."
    }
}

$pagesUrl = "$graphBase/me/accounts?fields=id,name,access_token,tasks&access_token=$([uri]::EscapeDataString($newLongUser))"
$pages = Invoke-GraphGet -Url $pagesUrl
$pageRows = @($pages.data)
$page = $pageRows | Where-Object { [string]$_.id -eq [string]$pageId } | Select-Object -First 1
if (-not $page) {
    throw "Page $pageId not returned from /me/accounts. Verify page permissions."
}

$newPageToken = [string]$page.access_token
if (-not $newPageToken) {
    throw "No page access token returned for $pageId"
}

$expiresAtUtc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn)

Save-UserEnv -Name "META_LONG_LIVED_USER_TOKEN" -Value $newLongUser
Save-UserEnv -Name "META_PAGE_ACCESS_TOKEN" -Value $newPageToken
Save-UserEnv -Name "META_TOKEN_EXPIRES_AT_UTC" -Value $expiresAtUtc.ToString("o")
Save-UserEnv -Name "META_TOKEN_UPDATED_AT_UTC" -Value (Get-Date).ToUniversalTime().ToString("o")

try {
    $igUrl = "$graphBase/$pageId?fields=instagram_business_account&access_token=$([uri]::EscapeDataString($newPageToken))"
    $ig = Invoke-GraphGet -Url $igUrl
    if ($ig.instagram_business_account.id) {
        Save-UserEnv -Name "META_IG_USER_ID" -Value ([string]$ig.instagram_business_account.id)
    }
}
catch {
    # Keep previous IG ID if present; this is optional for Facebook-only workflows.
}

if (-not $StateFile) {
    $StateFile = Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) "data") "marketing\meta_token_state.json"
}

try {
    $stateDir = Split-Path -Parent $StateFile
    if ($stateDir -and -not (Test-Path $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }
    $state = [ordered]@{
        updated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        expires_at_utc = $expiresAtUtc.ToString("o")
        page_id = $pageId
        long_user_token_masked = (Mask-Token $newLongUser)
        page_token_masked = (Mask-Token $newPageToken)
    }
    ($state | ConvertTo-Json -Depth 6) | Set-Content -Path $StateFile -Encoding UTF8
}
catch {
    Write-Warning "Could not write state file: $($_.Exception.Message)"
}

Write-Host "Meta token refresh successful." -ForegroundColor Green
Write-Host ("Long user token: " + (Mask-Token $newLongUser))
Write-Host ("Page token: " + (Mask-Token $newPageToken))
Write-Host ("Expires (UTC): " + $expiresAtUtc.ToString("u"))
