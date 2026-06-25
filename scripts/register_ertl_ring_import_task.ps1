param(
    [string]$TaskName = "AutoMedChemist_ErtlRingImport",
    [string]$Schedule = "Daily",
    [string]$At = "02:30",
    [int]$ChunkSize = 10000,
    [int]$MaxRuntimeSeconds = 1800
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$JobScript = Join-Path $Root "scripts\run_ertl_ring_import_job.ps1"
$Args = "-NoProfile -ExecutionPolicy Bypass -File `"$JobScript`" -ChunkSize $ChunkSize -MaxChunks 0 -MaxRuntimeSeconds $MaxRuntimeSeconds -MaxRetries 2"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Args -WorkingDirectory $Root

if ($Schedule -eq "Hourly") {
    $Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
} else {
    $Trigger = New-ScheduledTaskTrigger -Daily -At $At
}

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "AutoMedChemist DB-only Ertl 4M ring-system chunk importer." -Force | Out-Null
Write-Output "Registered scheduled task '$TaskName'."
