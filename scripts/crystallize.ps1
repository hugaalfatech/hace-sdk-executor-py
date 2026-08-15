# crystallize.ps1 — Build and crystallize executor-py artifact
# Produces: release/hace-executor-py-{version}.pyz

param(
    [switch]$Verbose,
    [string]$OutputDir = "release"
)

$ErrorActionPreference = "Stop"

Write-Host "=== executor-py Crystallization ===" -ForegroundColor Cyan

# Get version from pyproject.toml
$version = (Get-Content pyproject.toml | Select-String 'version\s*=').ToString().Split('"')[1]
if (-not $version) { $version = "0.1.0" }

Write-Host "Version: $version" -ForegroundColor Yellow

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

# 1. Run pre-flight checks
Write-Host "`n[1/6] Running pre-flight checks..." -ForegroundColor Yellow
& .\scripts\check.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Pre-flight checks failed"
    exit 1
}

# 2. Run full test suite
Write-Host "`n[2/6] Running test suite..." -ForegroundColor Yellow
& .\scripts\test.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests failed"
    exit 1
}

# 3. Compute FEH hash of source
Write-Host "`n[3/6] Computing FEH hash..." -ForegroundColor Yellow
$sourceFiles = Get-ChildItem src/executor_py -Recurse -File | Where-Object { $_.Extension -eq ".py" }
$hasher = [System.Security.Cryptography.SHA256]::Create()
foreach ($file in $sourceFiles) {
    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    $hasher.TransformBlock($bytes, 0, $bytes.Length, $null, 0)
}
$hasher.TransformFinalBlock([byte[]]@(), 0, 0)
$fehHash = ($hasher.Hash -join "").ToLower()
Write-Host "FEH: $fehHash" -ForegroundColor Green

# 4. Build PYZ artifact
Write-Host "`n[4/6] Building PYZ artifact..." -ForegroundColor Yellow
$artifactName = "hace-executor-py-$version.pyz"
$artifactPath = Join-Path $OutputDir $artifactName

# Use python -m zipfile to create executable PYZ
python -m zipfile -c $artifactPath src/executor_py
if ($LASTEXITCODE -ne 0) {
    Write-Error "PYZ creation failed"
    exit 1
}

# Add __main__.py for executable PYZ
$mainContent = @"
import sys
from executor_py import SimpleExecutor, ExecutorConfig

if __name__ == '__main__':
    print(f'executor-py v$version')
    print('Usage: python -m executor_py <rac_uri> <action> [payload_json]')
    sys.exit(0)
"@

# 5. Create manifest
Write-Host "`n[5/6] Creating manifest..." -ForegroundColor Yellow
$manifest = @{
    name = "hace-executor-py"
    version = $version
    feh_hash = $fehHash
    built_at = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
    fes_layer = "executor"
    actor = "text-ractor"
    capabilities = @(
        "ipo.execute",
        "ipo.input", 
        "ipo.process",
        "ipo.output",
        "fdi.autoload",
        "fdi.connect",
        "fdi.disconnect",
        "fdi.send",
        "fdi.recv",
        "fpi.discover",
        "fpi.pair",
        "fpi.unpair",
        "fpi.invoke",
        "fpi.broadcast",
        "capor.resolve",
        "racor.resolve_target",
        "racor.resolve_route",
    )
} | ConvertTo-Json -Depth 5

$manifestPath = Join-Path $OutputDir "manifest.json"
$manifest | Out-File -FilePath $manifestPath -Encoding utf8

# 6. Seal with ALR entry
Write-Host "`n[6/6] Sealing ALR entry..." -ForegroundColor Yellow
$alrEntry = @{
    execution_id = [System.Guid]::NewGuid().ToString()
    artifact = "hace-executor-py"
    version = $version
    feh_hash = $fehHash
    status = "crystallized"
    sealed_at = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
    authority = "CSA"
} | ConvertTo-Json -Depth 3

$alrPath = Join-Path $OutputDir "alr.json"
$alrEntry | Out-File -FilePath $alrPath -Encoding utf8

Write-Host "`n=== Crystallization Complete ===" -ForegroundColor Green
Write-Host "Artifact: $artifactPath" -ForegroundColor Cyan
Write-Host "FEH: $fehHash" -ForegroundColor Cyan
Write-Host "Manifest: $manifestPath" -ForegroundColor Cyan
Write-Host "ALR: $alrPath" -ForegroundColor Cyan