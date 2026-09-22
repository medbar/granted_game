param(
    [Parameter(Mandatory = $true)]
    [string]$GodotPath,
    [string]$UvPath = "",
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverRoot = Join-Path $projectRoot "server"
$clientRoot = Join-Path $projectRoot "client"

if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) {
    throw "Godot executable was not found at: $GodotPath"
}
$godot = (Resolve-Path -LiteralPath $GodotPath).Path
$verificationData = Join-Path $projectRoot ".verification\godot"
$env:APPDATA = Join-Path $verificationData "roaming"
$env:LOCALAPPDATA = Join-Path $verificationData "local"
New-Item -ItemType Directory -Path $env:APPDATA, $env:LOCALAPPDATA -Force | Out-Null
$uvCommand = $null
if (-not $SkipSync) {
    $uvCommand = if ($UvPath) {
        if (-not (Test-Path -LiteralPath $UvPath -PathType Leaf)) {
            throw "uv executable was not found at: $UvPath"
        }
        (Resolve-Path -LiteralPath $UvPath).Path
    }
    else {
        $command = Get-Command uv -ErrorAction SilentlyContinue
        if ($command) { $command.Source } else { $null }
    }
    if (-not $uvCommand) {
        throw "uv is required for verification unless -SkipSync is used with an existing server/.venv."
    }
}

Push-Location $serverRoot
try {
    if (-not $SkipSync) {
        & $uvCommand sync
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    }
    $python = Join-Path $serverRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "server/.venv is missing; run verification without -SkipSync first."
    }
    & $python scripts\quality_policy.py --root $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "OpenSpec/TDD/eval-first policy validation failed" }
    & $python -m pytest -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "backend tests failed" }
}
finally {
    Pop-Location
}

& $godot --headless --path $clientRoot --script res://tests/smoke_runner.gd
if ($LASTEXITCODE -ne 0) { throw "Godot client smoke tests failed" }
& $godot --headless --path $clientRoot --script res://tests/level_contract_runner.gd
if ($LASTEXITCODE -ne 0) { throw "Godot level JSON contract tests failed" }

$backend = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log") -WorkingDirectory $serverRoot -PassThru -WindowStyle Hidden
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
    & $godot --headless --path $clientRoot --script res://tests/ttfa_runner.gd
    if ($LASTEXITCODE -ne 0) { throw "client-observed TTFA SLO eval failed" }
    & $godot --path $clientRoot --script res://tests/environment_wish_runner.gd
    if ($LASTEXITCODE -ne 0) { throw "40-case visual environment eval failed" }
    & $godot --path $clientRoot --script res://tests/start_level_playthrough_runner.gd
    if ($LASTEXITCODE -ne 0) { throw "start-level visual playthrough failed" }
}
finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}

Write-Host "All Granted Game verification gates passed."
