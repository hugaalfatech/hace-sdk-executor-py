# check.ps1 — Pre-flight checks for executor-py
# Runs: typecheck, lint, basic validation

param(
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

Write-Host "=== executor-py Pre-flight Checks ===" -ForegroundColor Cyan

# 1. Check Python version
Write-Host "`n[1/5] Checking Python version..." -ForegroundColor Yellow
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python not found"
    exit 1
}

# 2. Check dependencies
Write-Host "`n[2/5] Checking dependencies..." -ForegroundColor Yellow
pip install -q -e ".[dev]" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Failed to install dev dependencies"
}

# 3. Type check with mypy
Write-Host "`n[3/5] Running mypy type check..." -ForegroundColor Yellow
mypy src/executor_py --strict --ignore-missing-imports
if ($LASTEXITCODE -ne 0) {
    Write-Error "Type check failed"
    exit 1
}
Write-Host "Type check passed" -ForegroundColor Green

# 4. Lint with ruff
Write-Host "`n[4/5] Running ruff lint..." -ForegroundColor Yellow
ruff check src/executor_py tests/
if ($LASTEXITCODE -ne 0) {
    Write-Error "Lint failed"
    exit 1
}
Write-Host "Lint passed" -ForegroundColor Green

# 5. Check canonical documents exist
Write-Host "`n[5/5] Checking canonical documents..." -ForegroundColor Yellow
$canonDir = ".know/canon"
$requiredDocs = @("FES.ail", "FAN.ail", "hookpoints.ail", "ASI.ail", "IPO.ail", "RAC_CONTRACTS.ail")
foreach ($doc in $requiredDocs) {
    $path = Join-Path $canonDir $doc
    if (Test-Path $path) {
        Write-Host "  ✓ $doc" -ForegroundColor Green
    } else {
        Write-Error "  ✗ Missing: $doc"
        exit 1
    }
}

Write-Host "`n=== All Pre-flight Checks Passed ===" -ForegroundColor Green