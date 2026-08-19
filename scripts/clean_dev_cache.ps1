# Clear dev caches for a fresh run (PowerShell)
# Usage: .\scripts\clean_dev_cache.ps1

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Cleaning caches under $root ..."

$targets = @(
    "$root\frontend\.next",
    "$root\.pytest_cache"
)

foreach ($t in $targets) {
    if (Test-Path $t) {
        Remove-Item -Recurse -Force $t
        Write-Host "  removed $t"
    }
}

Get-ChildItem -Path $root -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName
    Write-Host "  removed $($_.FullName)"
}

Write-Host "Done. Start backend: uvicorn app.main:app --reload"
Write-Host "Start frontend: cd frontend && npm run dev:clean"
