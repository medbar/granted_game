param(
    [string]$UvPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverRoot = Join-Path $projectRoot "server"

Push-Location $serverRoot
try {
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
    & $uvCommand sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    & $uvCommand run uvicorn app.main:app --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
