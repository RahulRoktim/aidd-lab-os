# ==============================================================================
# AIDD Lab OS — Native Scientific Runtime Validation Runner (Windows PowerShell)
# Usage: .\scripts\validate-native.ps1 [-Mode AUTO|DOCKER|CONDA|LOCAL] [-Cleanup]
# ==============================================================================

param (
    [string]$Mode = "AUTO",
    [switch]$Cleanup
)

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$env:PYTHONPATH = "$RootDir;$env:PYTHONPATH"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "AIDD LAB OS — LAUNCHING NATIVE SCIENTIFIC VALIDATION HARNESS" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

$argsList = @("--mode", $Mode)
if ($Cleanup) {
    $argsList += "--cleanup"
}

python validate_native_runtime.py @argsList
