param([ValidateSet('Dev', 'Build', 'Run')][string]$Mode = 'Run')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot 'apps\web'
Push-Location $webRoot
try {
    if ($Mode -eq 'Run') {
        $clientExe = Join-Path $webRoot 'src-tauri\target\release\agent-harbor.exe'
        if (-not (Test-Path -LiteralPath $clientExe)) { throw 'Build the desktop client first: scripts\desktop.ps1 -Mode Build' }
        & $clientExe
    } else {
        # Keep builds usable on workstations with limited Windows commit memory.
        if (-not $env:CARGO_BUILD_JOBS) { $env:CARGO_BUILD_JOBS = '1' }
        if (-not $env:NODE_OPTIONS) { $env:NODE_OPTIONS = '--max-old-space-size=1024' }
        if (-not $env:RAYON_NUM_THREADS) { $env:RAYON_NUM_THREADS = '1' }
        if ($Mode -eq 'Dev') { & pnpm.cmd run desktop:dev }
        else { & pnpm.cmd run desktop:build }
        if ($LASTEXITCODE -ne 0) { throw "Desktop command failed: $LASTEXITCODE" }
    }
} finally { Pop-Location }
