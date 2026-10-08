$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot '.runtime\processes.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No recorded AgentHarbor processes.'; exit 0 }
$state = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
if ($state.root -ne $projectRoot) { throw 'Process record belongs to a different directory.' }
foreach ($ownedPid in $state.pids) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ownedPid" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -and $process.CommandLine.Contains($projectRoot)) {
        taskkill.exe /PID $ownedPid /T /F | Out-Null
    } elseif ($process) {
        Write-Warning "PID $ownedPid no longer matches this project; leaving it running."
    }
}
Remove-Item -LiteralPath $pidFile
Write-Host 'AgentHarbor processes stopped.'
