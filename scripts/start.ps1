param([switch]$Build)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.env')) { throw 'Missing .env. Copy .env.example and configure local data/model paths and secrets first.' }
if (-not (Test-Path -LiteralPath 'artifacts\semantic_index\active.json')) { throw 'Missing semantic index. Follow docs/RUN_LOCAL.md to build it first.' }
& docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    $desktopApp = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $desktopApp)) { throw 'Docker Desktop is not available.' }
    Start-Process -FilePath $desktopApp -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        & docker info --format '{{.ServerVersion}}' 2>$null
        if ($LASTEXITCODE -eq 0) { break }
    }
}
if ($Build) { & docker compose build; if ($LASTEXITCODE -ne 0) { throw 'Image build failed.' } }
& docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed.' }
Write-Output 'CineWeave: http://localhost:13000'
Write-Output 'API documentation: http://localhost:18000/docs'
Write-Output 'Demo: demo@cineweave.local / CineweaveDemo!2026'
Write-Output 'Historical profile: history@cineweave.local / CineweaveDemo!2026'
Write-Output 'Use docker compose stop to stop services while retaining data.'
