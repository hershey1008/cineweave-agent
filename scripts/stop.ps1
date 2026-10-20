$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
& docker compose stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop CineWeave services.' }
Write-Output 'CineWeave stopped. Data volumes, models and indexes were retained.'
