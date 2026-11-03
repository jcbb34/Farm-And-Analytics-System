param(
    [switch]$SkipTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipDatabase,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "Jorros Backend"
$Frontend = Join-Path $Root "Jorros Frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

Write-Host "=== JoRoss Farm upgrade verification ===" -ForegroundColor Cyan
Write-Host "Database checks are read-only. Migrations are never applied automatically." -ForegroundColor Yellow

Push-Location $Backend
try {
    $OldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = "."

    Write-Host "`n[1] Python compilation" -ForegroundColor Cyan
    & $Python -m compileall -q app migrations tests
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }

    Write-Host "`n[2] Alembic heads" -ForegroundColor Cyan
    $Heads = @(& $Python -m alembic heads)
    if ($LASTEXITCODE -ne 0) { throw "Unable to read Alembic heads." }
    $Heads | ForEach-Object { Write-Host $_ }
    $HeadLines = @($Heads | Where-Object { $_ -match '\(head\)' })
    if ($HeadLines.Count -ne 1) {
        throw "Expected exactly one Alembic head in the supplied source."
    }
    $ExpectedHead = ($HeadLines[0] -split '\s+')[0]
    & $Python scripts/check_migrations.py
    if ($LASTEXITCODE -ne 0) { throw "Migration graph/rollback strategy check failed." }
    & $Python scripts/check_archive_api.py --local
    if ($LASTEXITCODE -ne 0) { throw "Archive API routes are missing from the backend source. Apply the complete backend folder." }
    & $Python scripts/check_event_planning_api.py --local
    if ($LASTEXITCODE -ne 0) { throw "Event/location API requirements are missing. Apply the complete backend folder." }

    if (-not $SkipDatabase) {
        Write-Host "`n[3] Current database revision, required schema and workflow uniqueness" -ForegroundColor Cyan
        & $Python scripts/check_installation.py
        if ($LASTEXITCODE -ne 0) { throw "Database schema verification failed. Review the checker output and upgrade instructions; no database changes were made by the check." }
    } else {
        Write-Host "`n[3] SQL Server revision check skipped by request" -ForegroundColor Yellow
    }

    if (-not $SkipTests) {
        Write-Host "`n[4] Backend tests" -ForegroundColor Cyan
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    } else {
        Write-Host "`n[4] Backend tests skipped by request" -ForegroundColor Yellow
    }
} finally {
    $env:PYTHONPATH = $OldPythonPath
    Pop-Location
}

Push-Location $Frontend
try {
    if (-not $SkipInstall) {
        Write-Host "`n[5] Install frontend dependencies from package-lock.json" -ForegroundColor Cyan
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    }
    Write-Host "`n[6] JavaScript/JSX source check" -ForegroundColor Cyan
    npm run check:source
    if ($LASTEXITCODE -ne 0) { throw "Frontend source check failed." }
    if (-not $SkipTests) {
        Write-Host "`n[7] Frontend tests" -ForegroundColor Cyan
        npm run test:frontend
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
    }
    if (-not $SkipFrontendBuild) {
        Write-Host "`n[8] Frontend production build" -ForegroundColor Cyan
        npm run build -- --webpack
        if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
    }
} finally {
    Pop-Location
}

$SkippedChecks = @()
if ($SkipDatabase) { $SkippedChecks += "database schema" }
if ($SkipTests) { $SkippedChecks += "tests" }
if ($SkipFrontendBuild) { $SkippedChecks += "production build" }
if ($SkippedChecks.Count -gt 0) {
    Write-Host "`nSelected checks completed. Skipped: $($SkippedChecks -join ', ')." -ForegroundColor Yellow
} else {
    Write-Host "`nAutomated source, test, build and database-schema checks completed." -ForegroundColor Green
}
Write-Host "Expected source Alembic head: $ExpectedHead" -ForegroundColor Cyan
Write-Host "Finish the device, workflow and recovery acceptance checks in the setup notes."
