# =========================================================================
#  EARNAPP AUTONOMOUS WATCHDOG FOR WINDOWS RDP
#  - Auto-Reboot routine every 6 hours
#  - Auto-Reboot if EarnApp streams <= 4 for 20 minutes
#  - Startup grace period (20 min) to prevent boot loops
# =========================================================================

$ErrorActionPreference = "SilentlyContinue"

$watchdogDir = "C:\EarnAppWatchdog"
if (-not (Test-Path $watchdogDir)) {
    New-Item -ItemType Directory -Path $watchdogDir -Force | Out-Null
}

$logFile   = "$watchdogDir\watchdog.log"
$stateFile = "$watchdogDir\state.json"

function Write-WatchdogLog([string]$message) {
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $logEntry = "[$timestamp] $message"
    try {
        Add-Content -Path $logFile -Value $logEntry -ErrorAction SilentlyContinue
        # Rotate log if larger than 1MB (keep last 500 lines)
        if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 1048576)) {
            $lines = Get-Content -Path $logFile -Tail 500
            Set-Content -Path $logFile -Value $lines -Force
        }
    } catch {}
    Write-Host $logEntry
}

function Get-StreamCount($pids) {
    if (-not $pids) { return 0 }
    try {
        $conns = Get-NetTCPConnection -State Established -ErrorAction Stop | Where-Object {
            $pids -contains $_.OwningProcess -and $_.RemoteAddress -ne "127.0.0.1" -and $_.RemoteAddress -ne "::1"
        }
        return ($conns | Measure-Object).Count
    } catch {
        # Fallback to netstat
        $count = 0
        try {
            $lines = netstat -ano | Select-String "ESTABLISHED"
            foreach ($line in $lines) {
                $parts = ($line.ToString().Trim() -split '\s+')
                if ($parts.Count -ge 5) {
                    $pidVal = $parts[4]
                    $remote = $parts[2]
                    if ($pids -contains [int]$pidVal -and -not $remote.StartsWith("127.0.0.1:") -and -not $remote.StartsWith("[::1]:")) {
                        $count++
                    }
                }
            }
        } catch {}
        return $count
    }
}

# --- 1. Hitung System Uptime ---
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$bootTime = if ($os) { $os.LastBootUpTime } else { Get-Date }
$uptimeMinutes = [Math]::Floor(((Get-Date) - $bootTime).TotalMinutes)
$uptimeHours = [Math]::Round(($uptimeMinutes / 60), 1)

# --- 2. Cek Jadwal Reboot Rutin 6 Jam (360 Menit) ---
$maxUptimeMinutes = 360
if ($uptimeMinutes -ge $maxUptimeMinutes) {
    Write-WatchdogLog "[REBOOT-6H] Uptime sistem telah mencapai $uptimeHours jam ($uptimeMinutes menit >= 360 menit). Menjalankan reboot rutin 6 jam..."
    # Hapus state agar bersih setelah reboot
    if (Test-Path $stateFile) { Remove-Item $stateFile -Force -ErrorAction SilentlyContinue }
    & shutdown.exe /r /t 15 /f /c "EarnApp Watchdog: Routine 6-hour reboot"
    exit
}

# --- 3. Baca / Inisialisasi State File ---
$state = @{
    LowStreamStart = ""
    LastCheck = (Get-Date).ToString("o")
    LastStreams = 0
    UptimeMinutes = $uptimeMinutes
}

if (Test-Path $stateFile) {
    try {
        $raw = Get-Content -Path $stateFile -Raw -ErrorAction Stop
        $parsed = $raw | ConvertFrom-Json -ErrorAction Stop
        if ($parsed) {
            $state.LowStreamStart = [string]$parsed.LowStreamStart
        }
    } catch {}
}

# --- 4. Masa Tenggang Setelah Booting (Grace Period 20 Menit) ---
# Berikan waktu 20 menit setelah mesin menyala agar EarnApp bisa start dan membangun koneksi
if ($uptimeMinutes -lt 20) {
    $remainingGrace = 20 - $uptimeMinutes
    Write-WatchdogLog "[GRACE-PERIOD] Uptime: $uptimeMinutes m (Masa pemanasan $remainingGrace m tersisa). Watchdog stream standby..."
    $state.LowStreamStart = ""
    $state.LastCheck = (Get-Date).ToString("o")
    $state | ConvertTo-Json | Set-Content -Path $stateFile -Force
    exit
}

# --- 5. Cek Proses & Koneksi EarnApp ---
$eaProcs = Get-Process -Name "*earnapp*" -ErrorAction SilentlyContinue
$isRunning = [bool]$eaProcs
$streams = 0

if ($isRunning) {
    $pids = $eaProcs.Id
    $streams = Get-StreamCount -pids $pids
} else {
    Write-WatchdogLog "[WARN] Proses EarnApp tidak terdeteksi berjalan!"
    # Coba jalankan EarnApp jika ada path instalasi
    $searchPaths = @(
        "C:\Program Files (x86)\EarnApp\earnapp.exe",
        "C:\Program Files\EarnApp\earnapp.exe",
        "$env:LOCALAPPDATA\Programs\EarnApp\earnapp.exe",
        "$env:APPDATA\EarnApp\earnapp.exe",
        "C:\ProgramData\EarnApp\earnapp.exe"
    )
    foreach ($sp in $searchPaths) {
        if (Test-Path $sp) {
            Write-WatchdogLog "[START] Menjalankan EarnApp dari: $sp"
            Start-Process -FilePath $sp -WindowStyle Minimized -ErrorAction SilentlyContinue
            break
        }
    }
}

$state.LastStreams = $streams
$state.LastCheck = (Get-Date).ToString("o")
$state.UptimeMinutes = $uptimeMinutes

# --- 6. Logika Stuck Stream (Streams <= 4 Selama 20 Menit) ---
if ($streams -le 4) {
    if ([string]::IsNullOrWhiteSpace($state.LowStreamStart)) {
        # Mulai hitung durasi low stream
        $state.LowStreamStart = (Get-Date).ToString("o")
        Write-WatchdogLog "[LOW-STREAM] Streams: $streams (<= 4). Timer stuck dimulai pada $($state.LowStreamStart)."
    } else {
        # Hitung berapa lama sudah stuck
        $startTime = [DateTime]::Parse($state.LowStreamStart)
        $stuckMinutes = [Math]::Floor(((Get-Date) - $startTime).TotalMinutes)
        Write-WatchdogLog "[LOW-STREAM] Streams: $streams (<= 4) selama $stuckMinutes / 20 menit (Uptime: $uptimeHours j)."

        if ($stuckMinutes -ge 20) {
            Write-WatchdogLog "[REBOOT-STUCK] Streams stuck di $streams (<= 4) selama $stuckMinutes menit (>= 20 menit)! Memicu auto reboot sekarang..."
            $state.LowStreamStart = ""
            $state | ConvertTo-Json | Set-Content -Path $stateFile -Force
            & shutdown.exe /r /t 15 /f /c "EarnApp Watchdog: Streams stuck <= 4 for 20 min"
            exit
        }
    }
} else {
    # Streams normal (> 4)
    if (-not [string]::IsNullOrWhiteSpace($state.LowStreamStart)) {
        Write-WatchdogLog "[RECOVERED] Streams kembali normal: $streams (> 4). Timer stuck direset ke 0."
    } else {
        Write-WatchdogLog "[OK] Normal | Streams: $streams | Uptime: $uptimeHours j / 6 j"
    }
    $state.LowStreamStart = ""
}

# Simpan state terkini
$state | ConvertTo-Json | Set-Content -Path $stateFile -Force
