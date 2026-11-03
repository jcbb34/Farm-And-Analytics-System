# JoRoss Farm safe source cleanup.
# Run this from the project root. It intentionally does NOT delete .env,
# .env.local, backups, generated reports, or imported source files.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$SafeTargets = @(
    (Join-Path $Root "Jorros Frontend\node_modules"),
    (Join-Path $Root "Jorros Frontend\.next"),
    (Join-Path $Root "Jorros Backend\.venv")
)

foreach ($Target in $SafeTargets) {
    if (Test-Path $Target) {
        Write-Host "Removing $Target"
        Remove-Item $Target -Recurse -Force
    }
}

Get-ChildItem -Path $Root -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "__pycache__" -or $_.Name -eq ".pytest_cache" } |
    ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item $_.FullName -Recurse -Force
    }

Get-ChildItem -Path $Root -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -eq ".pyc" } |
    ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item $_.FullName -Force
    }

Write-Host "Safe cleanup completed. Your .env/.env.local and runtime data were not deleted."
