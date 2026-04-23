param(
    [string]$TaskName = "FoliDataHarvester",
    [string]$ProjectDir = (Resolve-Path ".").Path
)

$Executable = Join-Path $ProjectDir ".venv\Scripts\foli-harvester.exe"
if (-not (Test-Path $Executable)) {
    throw "foli-harvester entry point was not found at '$Executable'. Run: uv sync"
}

$Action = New-ScheduledTaskAction `
    -Execute $Executable `
    -Argument "collect" `
    -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Collects Turku Foli SIRI data into Turso/libSQL." `
    -Force

Write-Host "Registered scheduled task '$TaskName'."
