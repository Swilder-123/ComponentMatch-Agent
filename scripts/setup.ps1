param(
    [ValidateSet('All', 'Backend', 'Frontend', 'Dev')]
    [string]$Target = 'All'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
$previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv is missing. Install uv first; see README.md, then open a new PowerShell window.'
    }
    $targets = if ($Target -eq 'All') { @('Backend', 'Frontend') } else { @($Target) }
    foreach ($item in $targets) {
        $environmentName = '.venv-' + $item.ToLowerInvariant()
        $env:UV_PROJECT_ENVIRONMENT = Join-Path $projectRoot $environmentName
        $syncArgs = @('--cache-dir', '.uv-cache', 'sync', '--locked', '--python', '3.11', '--link-mode', 'copy')
        if ($item -ne 'Dev') {
            $package = if ($item -eq 'Backend') { 'componentmatch-agent' } else { 'componentmatch-frontend' }
            $syncArgs += @('--package', $package, '--no-dev')
        }
        & uv @syncArgs
        if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed for $item" }
        Write-Host "$item environment ready: $environmentName"
    }
    if ($Target -in @('All', 'Backend', 'Dev')) {
        if (-not (Test-Path -LiteralPath '.env')) {
            Copy-Item -LiteralPath '.env.example' -Destination '.env'
            Write-Host 'Created .env from the blank template. Configure DEEPSEEK_API_KEY before matching.'
        }
    }
    Write-Host 'Setup complete. No database was changed and no model was called. Next steps: README.md.'
}
finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
    Pop-Location
}
