param(
    [string]$GodotPath = "",
    [string]$UvPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverRoot = Join-Path $projectRoot "server"
$clientRoot = Join-Path $projectRoot "client"

function Resolve-GodotExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw "Godot executable was not found at: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }
    foreach ($name in @("godot", "godot4")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "Godot 4.7.2 was not found. Pass -GodotPath with the full path to the executable."
}

$godot = Resolve-GodotExecutable $GodotPath
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
    throw "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/"
}

Push-Location $serverRoot
try {
    & $uvCommand sync
    if ($LASTEXITCODE -ne 0) {
        throw "Backend dependency setup failed."
    }
}
finally {
    Pop-Location
}

$python = Join-Path $serverRoot ".venv\Scripts\python.exe"
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
    if (-not $ready) {
        throw "The spell backend did not become ready."
    }
    & $godot --path $clientRoot
}
finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}
