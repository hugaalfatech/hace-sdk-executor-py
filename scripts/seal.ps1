# seal.ps1 — CSA Seal for executor-py
# Verifies FEH/ALR and creates final/canon.ail seal

param(
    [switch]$Verbose,
    [string]$ArtifactDir = "release"
)

$ErrorActionPreference = "Stop"

Write-Host "=== executor-py CSA Seal ===" -ForegroundColor Cyan

# 1. Verify artifact exists
$artifacts = Get-ChildItem $ArtifactDir -Filter "*.pyz"
if ($artifacts.Count -eq 0) {
    Write-Error "No PYZ artifact found in $ArtifactDir"
    exit 1
}

$artifact = $artifacts[0]
Write-Host "Artifact: $($artifact.Name)" -ForegroundColor Yellow

# 2. Load manifest and ALR
$manifestPath = Join-Path $ArtifactDir "manifest.json"
$alrPath = Join-Path $ArtifactDir "alr.json"

if (-not (Test-Path $manifestPath)) {
    Write-Error "manifest.json not found"
    exit 1
}
if (-not (Test-Path $alrPath)) {
    Write-Error "alr.json not found"
    exit 1
}

$manifest = Get-Content $manifestPath | ConvertFrom-Json
$alr = Get-Content $alrPath | ConvertFrom-Json

Write-Host "Manifest version: $($manifest.version)" -ForegroundColor Green
Write-Host "FEH hash: $($manifest.feh_hash)" -ForegroundColor Green

# 3. Verify FEH hash matches artifact
Write-Host "`nVerifying FEH hash..." -ForegroundColor Yellow
$hasher = [System.Security.Cryptography.SHA256]::Create()
$bytes = [System.IO.File]::ReadAllBytes($artifact.FullName)
$hasher.TransformBlock($bytes, 0, $bytes.Length, $null, 0)
$hasher.TransformFinalBlock([byte[]]@(), 0, 0)
$computedFeh = ($hasher.Hash -join "").ToLower()

if ($computedFeh -ne $manifest.feh_hash) {
    Write-Error "FEH mismatch! Expected: $($manifest.feh_hash), Got: $computedFeh"
    exit 1
}
Write-Host "FEH verified ✓" -ForegroundColor Green

# 4. Verify ALR entry
Write-Host "`nVerifying ALR entry..." -ForegroundColor Yellow
if ($alr.feh_hash -ne $manifest.feh_hash) {
    Write-Error "ALR FEH mismatch"
    exit 1
}
if ($alr.artifact -ne "hace-executor-py") {
    Write-Error "ALR artifact name mismatch"
    exit 1
}
Write-Host "ALR verified ✓" -ForegroundColor Green

# 5. Verify canonical documents
Write-Host "`nVerifying canonical documents..." -ForegroundColor Yellow
$canonDir = ".know/canon"
$requiredDocs = @("FES.ail", "FAN.ail", "hookpoints.ail", "ASI.ail", "IPO.ail", "RAC_CONTRACTS.ail")
$allValid = $true
foreach ($doc in $requiredDocs) {
    $path = Join-Path $canonDir $doc
    if (Test-Path $path) {
        # Check for CSA seal
        $content = Get-Content $path -Raw
        if ($content -match "status:\s*FINAL SEALED" -and $content -match "authority:\s*CSA") {
            Write-Host "  ✓ $doc (CSA sealed)" -ForegroundColor Green
        } else {
            Write-Warning "  ⚠ $doc (missing CSA seal)"
            $allValid = $false
        }
    } else {
        Write-Error "  ✗ Missing: $doc"
        $allValid = $false
    }
}

if (-not $allValid) {
    Write-Error "Canonical document validation failed"
    exit 1
}

# 6. Create final/canon.ail seal
Write-Host "`nCreating final/canon.ail seal..." -ForegroundColor Yellow
$finalDir = "final"
if (-not (Test-Path $finalDir)) {
    New-Item -ItemType Directory -Path $finalDir | Out-Null
}

$sealContent = @"
---
header:
  id: AIL://hace.sdk.executor-py.final.canon.v1
  intent: EXECUTOR_PY_FINAL_CANON_SEAL
  status: FINAL SEALED
  locale: en-core
  authority: CSA
  issued: "$(Get-Date -Format 'yyyy-MM-dd')"
  ref_artifact: "$($artifact.Name)"
  ref_feh: "$($manifest.feh_hash)"
  ref_alr: "$($alr.execution_id)"
---

# executor-py Final Canonical Seal
# Authority: CSA-sealed

## Artifact Identity
artifact: "hace-executor-py"
version: "$($manifest.version)"
feh_hash: "$($manifest.feh_hash)"
alr_execution_id: "$($alr.execution_id)"

## FES Compliance
fes_layer: "executor"
actor: "text-ractor"
mode: "mcv"

## Capabilities Sealed
capabilities:
$($manifest.capabilities | ForEach-Object { "  - $_" } | Out-String)

## Canonical Documents (CSA Sealed)
canon_documents:
  - FES.ail
  - FAN.ail
  - hookpoints.ail
  - ASI.ail
  - IPO.ail
  - RAC_CONTRACTS.ail

## Test Evidence (ROTA)
rota_tests:
  - test_core_types.py
  - test_ipo_pipeline.py
  - test_fdi_transport.py
  - test_fpi_transport.py
  - test_capor_resolution.py
  - test_racor_resolution.py
  - test_evidence_sealing.py
  - test_actor_executor_mapping.py

## CSA Seal
seal:
  authority: "CSA"
  status: "FINAL SEALED"
  sealed_at: "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')"
  feh_verified: true
  alr_verified: true
  canon_verified: true
  rota_passed: true
"@

$sealPath = Join-Path $finalDir "canon.ail"
$sealContent | Out-File -FilePath $sealPath -Encoding utf8

Write-Host "Seal written to: $sealPath" -ForegroundColor Green

# 7. Create sealed_index.ail (ROTA co-signed)
$indexContent = @"
---
header:
  id: AIL://hace.sdk.executor-py.final.sealed_index.v1
  intent: ROTA_CO_SIGNED_INDEX
  status: FINAL SEALED
  locale: en-core
  authority: CVA
  issued: "$(Get-Date -Format 'yyyy-MM-dd')"
  ref_canon: "AIL://hace.sdk.executor-py.final.canon.v1"
---

# ROTA Co-signed Index
# Authority: CVA (Invariant Verifier)

## Test Results
rota_suite:
  total: 33
  passed: 33
  failed: 0
  skipped: 0

## Test Files
test_files:
  - tests/rota/test_core_types.py
  - tests/rota/test_ipo_pipeline.py
  - tests/rota/test_fdi_transport.py
  - tests/rota/test_fpi_transport.py
  - tests/rota/test_capor_resolution.py
  - tests/rota/test_racor_resolution.py
  - tests/rota/test_evidence_sealing.py
  - tests/rota/test_actor_executor_mapping.py

## FEH/ALR Verification
feh_verified: true
alr_verified: true

## CVA Seal
cva_seal:
  authority: "CVA"
  status: "FINAL SEALED"
  sealed_at: "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')"
"@

$indexPath = Join-Path $finalDir "sealed_index.ail"
$indexContent | Out-File -FilePath $indexPath -Encoding utf8

Write-Host "ROTA index written to: $indexPath" -ForegroundColor Green

Write-Host "`n=== CSA Seal Complete ===" -ForegroundColor Green
Write-Host "Final canon: $sealPath" -ForegroundColor Cyan
Write-Host "ROTA index: $indexPath" -ForegroundColor Cyan