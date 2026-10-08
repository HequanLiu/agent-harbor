$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        uv venv .venv --python 3.11
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
    }
    uv pip install --python .venv\Scripts\python.exe -r requirements.lock -e 'vendor/agentscope[service,storage-sql,rag,vdb-qdrant,channel]'
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }
    Push-Location apps\web
    try {
        pnpm.cmd install --frozen-lockfile --prefer-offline
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    } finally { Pop-Location }
    Write-Host 'AgentHarbor installed. Run: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1'
} finally { Pop-Location }
