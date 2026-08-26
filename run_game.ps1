$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientRoot = Join-Path $projectRoot "client"
$godotCommand = Get-Command godot -ErrorAction SilentlyContinue

if (-not $godotCommand) {
    throw "Godot 4.7.2 is required. Add godot.exe to PATH or open client/project.godot from the Godot project manager."
}

& $godotCommand.Source --path $clientRoot

