param(
    [string]$TaskName = "AutoMedChemist_DailyMaintenance",
    [string]$At = "03:15"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$Script = Join-Path $Root "scripts\run_daily_maintenance.py"
$Args = "-NoProfile -ExecutionPolicy Bypass -Command `"Set-Location '$Root'; python -u '$Script'`""
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Args -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "AutoMedChemist daily data snapshot, warning governance, and closed-loop update." -Force | Out-Null
Write-Output "Registered scheduled task '$TaskName'."
