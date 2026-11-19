# Explicit opt-in only. Registers a LOCAL, research-only collector for the
# currently signed-in Windows account. No Render, fees, web UI or email.
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Remove,
    [switch]$Replace,
    [switch]$StartNow,
    [string]$TaskName = "EnergyBrew-News-Collector"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "This Task Scheduler installer requires Windows"
}
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Runner = (Resolve-Path (Join-Path $PSScriptRoot "run-energybrew-news.ps1")).Path
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($Remove) {
    if (-not $Task) {
        Write-Host "No registered EnergyBrew task to remove."
    } else {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed task $TaskName. Local research history was left untouched."
    }
    return
}
if (-not $Install) {
    Write-Host "PREVIEW ONLY: This script changes nothing unless -Install is passed."
    Write-Host "Task: $TaskName"
    Write-Host "User: $User (only while signed in)"
    Write-Host "Runner: $Runner"
    Write-Host "When: each sign-in; restart after failure; one instance maximum."
    Write-Host "Requirement: machine stays awake and online overnight."
    Write-Host "Use -Install to register, -Replace to overwrite an existing task."
    return
}
if ($Task -and -not $Replace) {
    throw "Task $TaskName already exists. Use -Replace explicitly to update."
}
Set-Location $Repo
& py -3.12 -c "from zoneinfo import ZoneInfo; import render_worker; assert ZoneInfo('America/Chicago')"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 with tzdata and collector imports is required."
}
$PowerShellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$ActionArgs = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $Runner + '"'
$Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $ActionArgs -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Params = @{
    TaskName = $TaskName
    Action = $Action
    Trigger = $Trigger
    Principal = $Principal
    Settings = $Settings
    Description = "EnergyBrew research-only energy news collection. No email or publishing."
}
if ($Replace) { $Params.Force = $true }
Register-ScheduledTask @Params | Out-Null
Write-Host "Registered $TaskName for $User. It runs at logon, not while logged off."
if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Start requested. Verify the live heartbeat; this is not an uptime guarantee."
}
