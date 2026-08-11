param(
    [string]$AppId,
    [string]$AppSecret,
    [string]$ShortLivedUserToken,
    [string]$PageId,
    [string]$IgUserId,
    [switch]$SkipScheduler,
    [int]$RefreshIntervalDays = 30,
    [string]$TaskName = "Infenergy Meta Token Refresh",
    [switch]$SkipValidation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Prompt-IfEmpty {
    param(
        [string]$Value,
        [string]$Prompt,
        [switch]$AsSecure
    )

    if ($Value -and $Value.Trim()) {
        return $Value.Trim()
    }


    if ($AsSecure) {
        $secure = Read-Host -Prompt $Prompt -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }

    return (Read-Host -Prompt $Prompt).Trim()
}

function Get-FirstAvailableEnv {
    param([string]$Name)
    $userValue = [Environment]::GetEnvironmentVariable($Name, "User")
    if ($userValue -and $userValue.Trim()) {
        return $userValue.Trim()
    }

    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($processValue -and $processValue.Trim()) {
        return $processValue.Trim()
    }

    return ""
}

function Mask-Token {
    param([string]$Token)
    if (-not $Token) { return "" }
    if ($Token.Length -le 12) { return "********" }
    return ($Token.Substring(0, 6) + "..." + $Token.Substring($Token.Length - 6))
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

function Save-UserEnv {
    param(
        [string]$Name,
        [string]$Value
    )
    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    Set-Item -Path ("Env:" + $Name) -Value $Value
}

$graphVersion = "v20.0"
$graphBase = "https://graph.facebook.com/$graphVersion"

Write-Section "Collect Inputs"
$existingAppId = Get-FirstAvailableEnv -Name "META_APP_ID"
$existingAppSecret = Get-FirstAvailableEnv -Name "META_APP_SECRET"
$existingToken = Get-FirstAvailableEnv -Name "META_LONG_LIVED_USER_TOKEN"
$existingPageId = Get-FirstAvailableEnv -Name "META_PAGE_ID"
$existingIgUserId = Get-FirstAvailableEnv -Name "META_IG_USER_ID"

if (-not $AppId) { $AppId = $existingAppId }
if (-not $AppSecret) { $AppSecret = $existingAppSecret }
if (-not $ShortLivedUserToken) { $ShortLivedUserToken = $existingToken }
if (-not $PageId) { $PageId = $existingPageId }
if (-not $IgUserId) { $IgUserId = $existingIgUserId }

$ShortLivedUserToken = Prompt-IfEmpty -Value $ShortLivedUserToken -Prompt "Meta User Access Token" -AsSecure
if (-not $ShortLivedUserToken) {
    throw "A Meta user access token is required."
}

$hasAppCredentials = ($AppId -and $AppId.Trim() -and $AppSecret -and $AppSecret.Trim())
$longUserToken = $ShortLivedUserToken
$expiresAtUtc = ""

if ($hasAppCredentials) {
    Write-Section "Exchange For Long-Lived User Token"
    $exchangeUrl = "$graphBase/oauth/access_token?grant_type=fb_exchange_token&client_id=$([uri]::EscapeDataString($AppId))&client_secret=$([uri]::EscapeDataString($AppSecret))&fb_exchange_token=$([uri]::EscapeDataString($ShortLivedUserToken))"
    try {
        $exchange = Invoke-GraphGet -Url $exchangeUrl
        $longUserToken = [string]$exchange.access_token
        $expiresIn = [int]$exchange.expires_in
        if (-not $longUserToken) {
            throw "Meta did not return a long-lived user token."
        }
        $expiresAtUtc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn).ToString("o")
        Write-Host ("Long-lived token acquired: " + (Mask-Token $longUserToken)) -ForegroundColor Green
        Write-Host ("Expires (UTC): " + ([datetime]$expiresAtUtc).ToString("u"))
    }
    catch {
        Write-Host "Exchange call failed; continuing with the token you provided." -ForegroundColor Yellow
        Write-Host "If this token is short-lived, provide a fresh one and App ID/Secret to enable auto-refresh." -ForegroundColor Yellow
        $longUserToken = $ShortLivedUserToken
    }
}
else {
    Write-Host "App ID/Secret not found. Using provided token as-is." -ForegroundColor Yellow
    Write-Host "Auto-refresh scheduling is disabled until META_APP_ID and META_APP_SECRET are configured." -ForegroundColor Yellow
}

if (-not $SkipValidation -and $hasAppCredentials) {
    Write-Section "Validate User Token"
    $appToken = "$AppId|$AppSecret"
    $debugUrl = "$graphBase/debug_token?input_token=$([uri]::EscapeDataString($longUserToken))&access_token=$([uri]::EscapeDataString($appToken))"
    $debug = Invoke-GraphGet -Url $debugUrl
    if (-not $debug.data.is_valid) {
        throw "Token validation failed. Token is not valid according to debug_token."
    }

    $scopes = @($debug.data.scopes)
    Write-Host ("Validated scopes: " + ($scopes -join ", "))
}

Write-Section "Resolve Page Access Token"
$pagesUrl = "$graphBase/me/accounts?fields=id,name,access_token,tasks&access_token=$([uri]::EscapeDataString($longUserToken))"
$pages = Invoke-GraphGet -Url $pagesUrl
$pageRows = @($pages.data)
if (-not $pageRows -or $pageRows.Count -eq 0) {
    throw "No managed pages were returned from /me/accounts. Ensure this user has Page access in Business Manager."
}

$PageId = $PageId.Trim()
if (-not $PageId) {
    if ($pageRows.Count -eq 1) {
        $PageId = [string]$pageRows[0].id
        Write-Host ("Auto-selected page: " + $pageRows[0].name + " (" + $PageId + ")") -ForegroundColor Green
    }
    else {
        Write-Host "Multiple managed pages found:" -ForegroundColor Yellow
        $pageRows | ForEach-Object { Write-Host (" - " + $_.name + " (" + $_.id + ")") }
        $PageId = Prompt-IfEmpty -Value "" -Prompt "Enter the Facebook Page ID to use"
    }
}

$page = $pageRows | Where-Object { [string]$_.id -eq [string]$PageId } | Select-Object -First 1
if (-not $page) {
    Write-Host "Managed pages returned:" -ForegroundColor Yellow
    $pageRows | ForEach-Object { Write-Host (" - " + $_.name + " (" + $_.id + ")") }
    throw "Configured PageId was not found in /me/accounts."
}

$pageToken = [string]$page.access_token
if (-not $pageToken) {
    throw "Could not resolve page access token for page id $PageId."
}
Write-Host ("Page token acquired: " + (Mask-Token $pageToken)) -ForegroundColor Green

Write-Section "Resolve Instagram Business Account (Optional)"
$igUserId = ""
try {
    $igUrl = "$graphBase/$PageId?fields=instagram_business_account&access_token=$([uri]::EscapeDataString($pageToken))"
    $ig = Invoke-GraphGet -Url $igUrl
    if ($ig.instagram_business_account.id) {
        $igUserId = [string]$ig.instagram_business_account.id
        Write-Host ("Instagram Business User ID: " + $igUserId) -ForegroundColor Green
    }
    else {
        if ($IgUserId) {
            $igUserId = $IgUserId.Trim()
            Write-Host ("Using provided Instagram User ID: " + $igUserId) -ForegroundColor Green
        }
        else {
            Write-Host "No instagram_business_account linked to this page. IG publishing will be skipped unless you provide META_IG_USER_ID." -ForegroundColor Yellow
        }
    }
}
catch {
    if ($IgUserId) {
        $igUserId = $IgUserId.Trim()
        Write-Host ("Lookup failed, using provided Instagram User ID: " + $igUserId) -ForegroundColor Green
    }
    else {
        Write-Host "Could not fetch instagram_business_account. Continuing without META_IG_USER_ID." -ForegroundColor Yellow
    }
}

Write-Section "Persist Environment Variables"
if ($AppId) {
    Save-UserEnv -Name "META_APP_ID" -Value $AppId
}
if ($AppSecret) {
    Save-UserEnv -Name "META_APP_SECRET" -Value $AppSecret
}
Save-UserEnv -Name "META_PAGE_ID" -Value $PageId
Save-UserEnv -Name "META_LONG_LIVED_USER_TOKEN" -Value $longUserToken
Save-UserEnv -Name "META_PAGE_ACCESS_TOKEN" -Value $pageToken
if ($expiresAtUtc) {
    Save-UserEnv -Name "META_TOKEN_EXPIRES_AT_UTC" -Value $expiresAtUtc
}
Save-UserEnv -Name "META_TOKEN_UPDATED_AT_UTC" -Value (Get-Date).ToUniversalTime().ToString("o")
if ($igUserId) {
    Save-UserEnv -Name "META_IG_USER_ID" -Value $igUserId
}

Write-Host "Saved user-scope environment variables for Meta publishing." -ForegroundColor Green

Write-Section "Create Scheduled Refresh Task"
if (-not $SkipScheduler -and $hasAppCredentials) {
    $scriptPath = Join-Path $PSScriptRoot "refresh_meta_tokens.ps1"
    if (-not (Test-Path $scriptPath)) {
        throw "Refresh script not found at $scriptPath"
    }

    if ($RefreshIntervalDays -lt 7) {
        throw "RefreshIntervalDays must be at least 7."
    }

    $weeksInterval = [Math]::Ceiling($RefreshIntervalDays / 7)
    if ($weeksInterval -lt 1) { $weeksInterval = 1 }
    if ($weeksInterval -gt 52) { $weeksInterval = 52 }

    $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval $weeksInterval -DaysOfWeek Monday -At 3am
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Refresh Meta long-lived user token and page token for Infenergy engine" -Force | Out-Null
        Write-Host ("Scheduled task registered: " + $TaskName) -ForegroundColor Green
    }
    catch {
        Write-Host "Could not register scheduled task automatically (often requires elevated PowerShell)." -ForegroundColor Yellow
        Write-Host "Run this manually in elevated PowerShell:" -ForegroundColor Yellow
        Write-Host "Register-ScheduledTask -TaskName '$TaskName' -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File \"$scriptPath\"') -Trigger (New-ScheduledTaskTrigger -Weekly -WeeksInterval $weeksInterval -DaysOfWeek Monday -At 3am) -Force"
    }
}
elseif (-not $hasAppCredentials) {
    Write-Host "Scheduler step skipped because META_APP_ID and META_APP_SECRET are not configured yet." -ForegroundColor Yellow
}
else {
    Write-Host "Scheduler step skipped." -ForegroundColor Yellow
}

Write-Section "Done"
Write-Host "Meta token automation is configured."
Write-Host "You can run the refresher anytime:" 
$refreshPath = Join-Path $PSScriptRoot "refresh_meta_tokens.ps1"
Write-Host (("powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`"") -f $refreshPath)
