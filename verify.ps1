param(
    [Parameter(Mandatory = $true)]
    [string]$GodotPath,
    [string]$UvPath = "",
    [switch]$SkipSync,
    [ValidateSet("legal", "legacy_genie")]
    [string]$Profile = "legal"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverRoot = Join-Path $projectRoot "server"
$clientRoot = Join-Path $projectRoot "client"
if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) { throw "Godot executable not found: $GodotPath" }
$godot = (Resolve-Path -LiteralPath $GodotPath).Path
$verificationData = Join-Path $projectRoot ".verification"
New-Item -ItemType Directory -Path $verificationData -Force | Out-Null
$uvCommand = $null
if (-not $SkipSync) {
    $uvCommand = if ($UvPath) { (Resolve-Path -LiteralPath $UvPath).Path } else {
        $command = Get-Command uv -ErrorAction SilentlyContinue
        if ($command) { $command.Source } else { $null }
    }
    if (-not $uvCommand) { throw "uv is required unless -SkipSync is used with an existing server/.venv." }
}

function Assert-Command([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

Push-Location $serverRoot
try {
    if (-not $SkipSync) {
        & $uvCommand sync
        Assert-Command "uv sync failed"
    }
    $python = Join-Path $serverRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "server/.venv is missing" }
    & $python scripts\quality_policy.py --root $projectRoot --profile $Profile --print-gates
    Assert-Command "OpenSpec/TDD/eval-first policy validation failed"
    $testTemp = Join-Path $verificationData ("p-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    & $python -m pytest -p no:cacheprovider --basetemp $testTemp
    Assert-Command "server tests failed"
    if ($Profile -eq "legal") {
        & $python scripts\run_legal_evals.py --mode frozen
        Assert-Command "frozen legal-world eval failed"
        & $python scripts\run_legal_evals.py --mode live
        Assert-Command "live legal-world eval failed"
    }
}
finally { Pop-Location }

if ($Profile -eq "legal") {
    & $godot --headless --path $clientRoot --script res://tests/legal_smoke_runner.gd
    Assert-Command "legal campaign smoke failed"
} else {
    & $godot --headless --path $clientRoot --script res://tests/smoke_runner.gd
    Assert-Command "legacy smoke failed"
    & $godot --headless --path $clientRoot --script res://tests/level_contract_runner.gd
    Assert-Command "legacy level contract failed"
}

# An isolated legal test server never attaches to or stops the user's game server.
$port = if ($Profile -eq "legal") { 8003 } else { 8000 }
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
try { $listener.Start() }
catch { throw "Verification port $port is already in use. The existing server was not touched." }
finally { $listener.Stop() }
$previousBureauUrl = $env:BUREAU_API_URL
$runId = [guid]::NewGuid().ToString("N").Substring(0, 8)
$stdout = Join-Path $verificationData ("backend-" + $runId + ".out.log")
$stderr = Join-Path $verificationData ("backend-" + $runId + ".err.log")
$backend = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$port", "--no-access-log") -WorkingDirectory $serverRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        $backend.Refresh()
        if ($backend.HasExited) { throw "Verification backend exited. See $stderr" }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 1
            if ($health.status -eq "ok") { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $ready) { throw "Verification backend did not become ready. See $stderr" }
    if ($Profile -eq "legal") {
        $env:BUREAU_API_URL = "http://127.0.0.1:$port"
        foreach ($runner in @("daily_routine_runner.gd", "bureaucracy_runner.gd")) {
            & $godot --path $clientRoot --audio-driver Dummy --script ("res://tests/" + $runner)
            Assert-Command "legal $runner failed"
        }
    } else {
        Push-Location $serverRoot
        try {
            $generations = @(Get-ChildItem runtime/evolution/generation-*.json -ErrorAction SilentlyContinue |
                ForEach-Object { if ($_.BaseName -match '^generation-(\d+)$') { [int]$Matches[1] } })
            $nextGeneration = if ($generations.Count) { ($generations | Measure-Object -Maximum).Maximum + 1 } else { 1 }
            & $python scripts\run_agent_evolution.py --generation $nextGeneration
            Assert-Command "legacy environment evolution failed"
            & $python scripts\run_monty_evals.py
            Assert-Command "legacy Monty eval failed"
            & $python scripts\run_agent_levels.py --concurrency 1 --max-turns 4
            Assert-Command "legacy agent-level eval failed"
        } finally { Pop-Location }
        foreach ($runner in @("live_cast_runner.gd", "ttfa_runner.gd")) {
            & $godot --headless --path $clientRoot --script ("res://tests/" + $runner)
            Assert-Command "legacy $runner failed"
        }
        foreach ($runner in @("environment_wish_runner.gd", "start_level_playthrough_runner.gd")) {
            & $godot --path $clientRoot --audio-driver Dummy --script ("res://tests/" + $runner)
            Assert-Command "legacy $runner failed"
        }
    }
}
finally {
    $env:BUREAU_API_URL = $previousBureauUrl
    $backend.Refresh()
    if (-not $backend.HasExited) {
        # Windows venv launchers can own a separate Python worker. Stop only this server's children.
        Get-CimInstance Win32_Process -Filter ("ParentProcessId = " + $backend.Id) |
            Where-Object { $_.Name -in @("python.exe", "pythonw.exe") } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "All automated $Profile gates passed. Review the saved trajectories/PNG before archiving."
