param([int]$ApiPort = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($ApiPort -lt 1024 -or $ApiPort -gt 65535) { throw 'ApiPort must be between 1024 and 65535.' }
$interpreter = Join-Path $projectRoot '.venv-backend/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $interpreter)) { throw 'Run scripts/setup.ps1 -Target Backend first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $interpreter scripts/start_backend.py --port $ApiPort
    exit $LASTEXITCODE
}
finally { Pop-Location }
