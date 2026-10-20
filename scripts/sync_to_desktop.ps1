param([switch]$WithArtifacts)
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$targetRoot = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('Desktop')) 'cineweave-agent'))
if ($targetRoot -eq $sourceRoot) { throw 'Source and destination are identical.' }
if (-not (Test-Path -LiteralPath $targetRoot)) { New-Item -ItemType Directory -Path $targetRoot | Out-Null }
function Copy-RelativeFile([string]$relative) {
    $sourceFile = [IO.Path]::GetFullPath((Join-Path $sourceRoot $relative))
    $targetFile = [IO.Path]::GetFullPath((Join-Path $targetRoot $relative))
    if (-not $sourceFile.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Source path escaped workspace.' }
    if (-not $targetFile.StartsWith($targetRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Destination path escaped target folder.' }
    $parent = Split-Path -Parent $targetFile
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
}
$files = & git -c "safe.directory=$sourceRoot" -C $sourceRoot ls-files --cached --others --exclude-standard
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate project source files.' }
foreach ($file in $files) { if (Test-Path -LiteralPath (Join-Path $sourceRoot $file) -PathType Leaf) { Copy-RelativeFile $file } }
if ((Test-Path -LiteralPath (Join-Path $sourceRoot '.env')) -and -not (Test-Path -LiteralPath (Join-Path $targetRoot '.env'))) { Copy-RelativeFile '.env' }
foreach ($folder in @('frontend\dist', 'evaluation\reports\generated')) {
    $path = Join-Path $sourceRoot $folder
    if (Test-Path -LiteralPath $path) {
        Get-ChildItem -LiteralPath $path -Recurse -File | ForEach-Object { Copy-RelativeFile ([IO.Path]::GetRelativePath($sourceRoot, $_.FullName)) }
    }
}
if ($WithArtifacts) {
    $model = Join-Path $sourceRoot 'artifacts\model_cache\bge-m3'
    Get-ChildItem -LiteralPath $model -Recurse -File | Where-Object {
        $_.FullName -notlike '*\weight_chunks\*' -and $_.Name -notlike '*.part' -and $_.Name -notlike '*.verified-download'
    } | ForEach-Object { Copy-RelativeFile ([IO.Path]::GetRelativePath($sourceRoot, $_.FullName)) }
    $index = Join-Path $sourceRoot 'artifacts\semantic_index'
    Copy-RelativeFile 'artifacts\semantic_index\active.json'
    $version = (Get-Content -LiteralPath (Join-Path $index 'active.json') -Raw | ConvertFrom-Json).version
    if ($version -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid index version.' }
    Get-ChildItem -LiteralPath (Join-Path $index $version) -Recurse -File | ForEach-Object { Copy-RelativeFile ([IO.Path]::GetRelativePath($sourceRoot, $_.FullName)) }
}
Write-Output ('CineWeave source synchronized to ' + $targetRoot)
