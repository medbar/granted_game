param(
    [Parameter(Mandatory = $true)]
    [string]$GodotPath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverRoot = Join-Path $projectRoot "server"
$clientRoot = Join-Path $projectRoot "client"

if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) {
    throw "Godot executable was not found at: $GodotPath"
}
$godot = (Resolve-Path -LiteralPath $GodotPath).Path
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    throw "uv is required for verification."
}

Push-Location $serverRoot
try {
    & $uv.Source sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    & $uv.Source run pytest -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "backend tests failed" }
}
finally {
    Pop-Location
}

& $godot --headless --path $clientRoot --script res://tests/smoke_runner.gd
if ($LASTEXITCODE -ne 0) { throw "Godot client smoke tests failed" }

$python = Join-Path $serverRoot ".venv\Scripts\python.exe"
$backend = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $serverRoot -PassThru -WindowStyle Hidden
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1
            if ($health.status -eq "ok") {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 200
        }
    }
    if (-not $ready) { throw "backend did not become ready for live integration tests" }
    & $godot --headless --path $clientRoot --script res://tests/live_cast_runner.gd
    if ($LASTEXITCODE -ne 0) { throw "live Godot/FastAPI tests failed" }
}
finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}

Write-Host "All Granted Game verification gates passed."

