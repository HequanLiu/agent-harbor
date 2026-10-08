$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$viteScript = Join-Path $projectRoot 'apps\web\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $pythonExe) -or -not (Test-Path -LiteralPath $viteScript)) { throw 'Run scripts\setup.ps1 first.' }
$settings = @{}
$envPath = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envPath) {
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*(HARBOR_[A-Z_]+)\s*=\s*(.*?)\s*$') { $settings[$Matches[1]] = $Matches[2].Trim('"', "'") }
    }
}
$apiPort = if ($settings.ContainsKey('HARBOR_API_PORT')) { [int]$settings['HARBOR_API_PORT'] } else { 8017 }
$webPort = if ($settings.ContainsKey('HARBOR_WEB_PORT')) { [int]$settings['HARBOR_WEB_PORT'] } else { 5177 }
foreach ($port in @($apiPort, $webPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is occupied. Change .env or stop the project's previous run." }
}
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$processes = @()
try {
    $serverMain = Join-Path $projectRoot 'apps\server\main.py'
    $server = Start-Process -FilePath $pythonExe -ArgumentList @('-X', 'utf8', ('"' + $serverMain + '"')) -WorkingDirectory (Join-Path $projectRoot 'apps\server') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'server.out.log') -RedirectStandardError (Join-Path $runtimeDir 'server.err.log')
    $processes += $server.Id
    $web = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @(('"' + $viteScript + '"')) -WorkingDirectory (Join-Path $projectRoot 'apps\web') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'web.out.log') -RedirectStandardError (Join-Path $runtimeDir 'web.err.log')
    $processes += $web.Id
    @{ root = $projectRoot; pids = $processes } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'processes.json') -Encoding UTF8
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        Start-Sleep -Seconds 1
        if ($server.HasExited -or $web.HasExited) { throw "A service exited. Inspect $runtimeDir logs." }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$webPort/api/harbor/health" -TimeoutSec 2
            if ($health.name -eq 'AgentHarbor') { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw "Startup timed out. Inspect $runtimeDir logs." }
    Write-Host "AgentHarbor: http://127.0.0.1:$webPort"
    Write-Host "API: http://127.0.0.1:$apiPort"
    Write-Host 'Stop with: powershell -ExecutionPolicy Bypass -File scripts\stop.ps1'
} catch {
    foreach ($ownedPid in $processes) { taskkill.exe /PID $ownedPid /T /F 2>$null | Out-Null }
    throw
}
