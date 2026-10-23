param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 8501,
    [switch]$CheckOnly,
    [switch]$SmokeTest
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv is required. Install uv and rerun this script.'
    }
    & (Join-Path $PSScriptRoot 'setup.ps1')
    $launchArgs = @('scripts/start_demo.py', '--api-port', "$ApiPort", '--ui-port', "$UiPort")
    $launchArgs += @('--frontend-python', (Join-Path $projectRoot '.venv-frontend/Scripts/python.exe'))
    if ($CheckOnly) { $launchArgs += '--check-only' }
    if ($SmokeTest) { $launchArgs += '--smoke-test' }
    & .\.venv-backend\Scripts\python.exe @launchArgs
    exit $LASTEXITCODE
}
finally { Pop-Location }
