param(
    [int]$ChunkSize = 10000,
    [int]$MaxChunks = 1,
    [int]$MaxRuntimeSeconds = 1800,
    [int]$SleepSeconds = 0,
    [int]$MaxRetries = 2
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$LogDir = Join-Path $Root "data\substituents"
$LogPath = Join-Path $LogDir "ertl_ring_import_task.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-JobLog {
    param([string]$Message)
    $stamp = (Get-Date).ToUniversalTime().ToString("o")
    "$stamp $Message" | Tee-Object -FilePath $LogPath -Append
}

$attempt = 0
while ($attempt -le $MaxRetries) {
    $attempt += 1
    try {
        Write-JobLog "Starting Ertl ring import attempt $attempt."
        & python -u (Join-Path $Root "scripts\import_ertl_ring_chunks.py") `
            --chunk-size $ChunkSize `
            --max-chunks $MaxChunks `
            --continuous `
            --sleep-seconds $SleepSeconds `
            --max-runtime-seconds $MaxRuntimeSeconds `
            --report-out (Join-Path $LogDir "ertl_ring_chunk_import_report.json")
        if ($LASTEXITCODE -ne 0) {
            throw "import_ertl_ring_chunks.py exited with $LASTEXITCODE"
        }
        & python -u (Join-Path $Root "scripts\ring_import_status.py") --out (Join-Path $LogDir "ring_import_status.json")
        Write-JobLog "Ertl ring import completed."
        exit 0
    } catch {
        Write-JobLog "Attempt $attempt failed: $($_.Exception.Message)"
        if ($attempt -gt $MaxRetries) {
            & python -u (Join-Path $Root "scripts\ring_import_status.py") --out (Join-Path $LogDir "ring_import_status.json")
            exit 1
        }
        Start-Sleep -Seconds ([Math]::Min(300, 30 * $attempt))
    }
}
