# test.ps1 — Full test suite for executor-py
# Runs: unit tests, integration tests, ROTA audit

param(
    [switch]$Verbose,
    [switch]$RotaOnly,
    [switch]$UnitOnly,
    [switch]$Coverage
)

$ErrorActionPreference = "Stop"

Write-Host "=== executor-py Test Suite ===" -ForegroundColor Cyan

# Install test dependencies
Write-Host "`n[0] Installing test dependencies..." -ForegroundColor Yellow
pip install -q pytest pytest-asyncio pytest-cov 2>$null

$pytestArgs = @("tests/")
if ($Verbose) { $pytestArgs += "-v" }
if ($Coverage) { $pytestArgs += "--cov=executor_py --cov-report=term-missing" }

if ($RotaOnly) {
    Write-Host "`nRunning ROTA tests only..." -ForegroundColor Yellow
    $pytestArgs = @("tests/rota/", "-v")
} elseif ($UnitOnly) {
    Write-Host "`nRunning unit tests only..." -ForegroundColor Yellow
    $pytestArgs = @("tests/", "-v", "--ignore=tests/rota")
}

# Run tests
Write-Host "`nExecuting: pytest $($pytestArgs -join ' ')" -ForegroundColor Cyan
pytest @pytestArgs

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "`n=== All Tests Passed ===" -ForegroundColor Green
} else {
    Write-Error "`n=== Tests Failed ==="
}

exit $exitCode