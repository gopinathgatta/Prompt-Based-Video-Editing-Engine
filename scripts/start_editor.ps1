param(
    [int]$Port = 8000,
    [string]$DataDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'work\runtime_data')
)

$ErrorActionPreference = 'Stop'
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$pythonLauncher = (Get-Command py -ErrorAction Stop).Source
$env:PS2_HOST = '127.0.0.1'
$env:PS2_PORT = [string]$Port
$env:PS2_DATA_DIR = $DataDirectory

$existing = $null
try { $existing = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1 } catch {}
if ($existing) {
    Start-Process "http://127.0.0.1:$Port"
    Write-Host "Editor already running: http://127.0.0.1:$Port"
    exit 0
}

$server = Start-Process -FilePath $pythonLauncher -ArgumentList '-m','app.server' -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden
$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1
        if ($health) { $ready = $true; break }
    } catch {}
    if ($server.HasExited) { throw "Editor process exited with code $($server.ExitCode)." }
}
if (-not $ready) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    throw "Editor did not become ready on port $Port. Start manually with: py -m app.server"
}

Start-Process "http://127.0.0.1:$Port"
Write-Host "Editor is ready: http://127.0.0.1:$Port"
Write-Host "Server PID: $($server.Id). Stop it with: Stop-Process -Id $($server.Id)"
