param([string]$PlanPath = (Join-Path $PSScriptRoot '..\docs\media\video-plan.json'))
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$output = Join-Path $root '.runtime\video-audio'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding utf8 | ConvertFrom-Json
$voice = New-Object -ComObject SAPI.SpVoice
$selected = @($voice.GetVoices() | Where-Object { $_.GetDescription() -match 'Huihui' })
if ($selected.Count -eq 0) { throw 'Microsoft Huihui Chinese desktop voice is required for this offline narration script.' }
$voice.Voice = $selected[0]
$voice.Rate = 2
foreach ($scene in $plan.scenes) {
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Format.Type = 22
    $path = Join-Path $output ($scene.id + '.wav')
    $stream.Open($path, 3, $false)
    try {
        $voice.AudioOutputStream = $stream
        [void]$voice.Speak($scene.narration)
    } finally { $stream.Close() }
    Write-Output ('Narration saved: ' + $scene.id)
}
