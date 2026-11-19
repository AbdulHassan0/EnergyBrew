# Optional free local news collector. NEVER emails or publishes.
param(
    [string]$Python = "py",
    [string]$StateRoot = "$env:LOCALAPPDATA\EnergyBrew\NewsState"
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Test-Path $StateRoot)) {
    New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
}
Set-Location $Repo
$env:PYTHONUNBUFFERED = "1"
Write-Host "EnergyBrew research-only collector. Local state: $StateRoot"
if ($Python -eq "py") {
    & py -3.12 "$Repo\render_worker.py" --root "$StateRoot"
} else {
    & $Python "$Repo\render_worker.py" --root "$StateRoot"
}
if ($LASTEXITCODE -ne 0) {
    throw "Collector exited with status $LASTEXITCODE"
}
