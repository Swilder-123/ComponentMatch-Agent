param([int]$UiPort = 8501, [string]$ApiUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$interpreter = Join-Path $projectRoot '.venv-frontend/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $interpreter)) { throw 'Run scripts/setup.ps1 -Target Frontend first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $interpreter frontend/run.py --port $UiPort --api-url $ApiUrl
    exit $LASTEXITCODE
}
finally { Pop-Location }
