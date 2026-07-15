<#
.SYNOPSIS
    One-shot local setup for the AI Agentic QE Platform (no admin required).

.DESCRIPTION
    Creates the backend Python virtual environment, installs backend and
    frontend dependencies, and seeds backend\.env from the example if missing.
    Safe to re-run (idempotent). Does NOT need administrator rights.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup.ps1

.NOTES
    Prerequisites (install per-user, no admin): Python 3.11+ on PATH, and
    Node.js/npm on PATH. See docs\RESTRICTED-LAPTOP.md.
#>

$ErrorActionPreference = "Stop"

# Always operate relative to this script's location, wherever it is run from.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "    $msg" -ForegroundColor Yellow }

function Get-Exe($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

Write-Host "AI Agentic QE Platform - local setup" -ForegroundColor White
Write-Host "Repo root: $Root"

# --- Prerequisite checks -------------------------------------------------
Write-Step "Checking prerequisites"

$python = Get-Exe "python"
if (-not $python) { $python = Get-Exe "py" }
if (-not $python) {
    throw "Python not found on PATH. Install Python 3.11+ per-user (tick 'Add python.exe to PATH') and re-run. See docs\RESTRICTED-LAPTOP.md."
}
$pyVer = (& $python --version) 2>&1
Write-Ok "Python: $pyVer ($python)"

$npm = Get-Exe "npm"
if (-not $npm) {
    throw "npm not found on PATH. Extract the Node.js Windows .zip and add its folder to your user PATH, then re-run. See docs\RESTRICTED-LAPTOP.md."
}
$npmVer = (& $npm --version) 2>&1
Write-Ok "npm: $npmVer ($npm)"

# --- Backend: venv + deps ------------------------------------------------
Write-Step "Backend: virtual environment"
$venv = Join-Path $Backend ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"
if (Test-Path $venvPy) {
    Write-Ok ".venv already exists - reusing"
} else {
    & $python -m venv $venv
    Write-Ok "created .venv"
}

Write-Step "Backend: installing dependencies (pip)"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $Backend "requirements.txt")
Write-Ok "backend dependencies installed"

# --- Backend: .env -------------------------------------------------------
Write-Step "Backend: .env configuration"
$envFile = Join-Path $Backend ".env"
$envExample = Join-Path $Backend ".env.example"
if (Test-Path $envFile) {
    Write-Ok ".env already exists - left untouched"
} elseif (Test-Path $envExample) {
    Copy-Item $envExample $envFile
    Write-Warn2 "created backend\.env from .env.example - it starts in DEMO mode."
    Write-Warn2 "Edit it to add ANTHROPIC_API_KEY / Jira creds and set DEMO_MODE=false for live mode."
} else {
    Write-Warn2 ".env.example not found - skipping .env creation."
}

# --- Frontend: deps ------------------------------------------------------
Write-Step "Frontend: installing dependencies (npm)"
Push-Location $Frontend
try {
    & $npm install
    Write-Ok "frontend dependencies installed"
} finally {
    Pop-Location
}

# --- Done ----------------------------------------------------------------
Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host @"

Next steps - run these in two separate terminals:

  # Terminal 1 - backend
  cd "$Backend"
  .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

  # Terminal 2 - frontend
  cd "$Frontend"
  npm run dev

Then open http://localhost:5173  (backend health: http://127.0.0.1:8000/health)
"@ -ForegroundColor White
