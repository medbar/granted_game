$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverRoot = Join-Path $projectRoot "server"

Push-Location $serverRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/"
    }
    uv sync
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}

