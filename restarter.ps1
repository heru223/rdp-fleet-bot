# =========================================================================
#  EARNAPP AUTONOMOUS SOFT-RESTARTER & STREAM WATCHDOG
#  - Otomatis restart EarnApp tiap 6 jam
#  - Otomatis restart EarnApp jika stream <= 4 selama 20 menit
#  - Flush DNS & refresh koneksi
#  - TANPA REBOOT OS (RDP aman 24/7 tanpa risiko mati / harus buka panel)
# =========================================================================

$ErrorActionPreference = "SilentlyContinue"

# Pastikan hanya 1 instance yang berjalan (Mutex)
$mutex = New-Object System.Threading.Mutex($false, "Global\EarnAppRestarterMutex")
if (-not $mutex.WaitOne(0, $false)) {
    Write-Host "EarnApp Restarter sudah berjalan di background."
    exit
}

$workDir = "C:\EarnAppRestarter"
if (-not (Test-Path $workDir)) {
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
}

$logFile   = "$workDir\restarter.log"
$stateFile = "$workDir\state.json"

function Write-RestarterLog([string]$message) {
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $entry = "[$timestamp] $message"
    try {
        Add-Content -Path $logFile -Value $entry -ErrorAction SilentlyContinue
        # Rotasi log jika lebih dari 1 MB (simpan 500 baris terakhir)
        if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 1048576)) {
            $lines = Get-Content -Path $logFile -Tail 500
            Set-Content -Path $logFile -Value $lines -Force
        }
    } catch {}
    Write-Host $entry
}

function Find-EarnAppExe {
    # 1. Cek dari proses aktif
    $ea = Get-Process -Name "*earnapp*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ea) {
        try {
            $p = $ea.MainModule.FileName
            if ($p -and (Test-Path $p)) { return $p }
        } catch {}
        try {
            $p = $ea.Path
            if ($p -and (Test-Path $p)) { return $p }
        } catch {}
    }

    # 2. Cek lokasi instalasi standar
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\EarnApp\earnapp.exe",
        "C:\Program Files (x86)\EarnApp\earnapp.exe",
        "C:\Program Files\EarnApp\earnapp.exe",
        "$env:APPDATA\EarnApp\earnapp.exe",
        "C:\ProgramData\EarnApp\earnapp.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    # 3. Cek dari Registry
    $regPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run",
        "HKCU:\Software\EarnApp",
        "HKLM:\Software\EarnApp"
    )
    foreach ($rp in $regPaths) {
        try {
            $props = Get-ItemProperty -Path $rp -ErrorAction SilentlyContinue
            if ($props.EarnApp) {
                $clean = $props.EarnApp.Trim('"')
                if (Test-Path $clean) { return $clean }
            }
        } catch {}
    }

    return $null
}

function Get-ActiveStreams {
    $eaProcs = Get-Process -Name "*earnapp*" -ErrorAction SilentlyContinue
    if (-not $eaProcs) { return 0 }
    
    $pids = $eaProcs.Id
    try {
        $conns = Get-NetTCPConnection -State Established -ErrorAction Stop | Where-Object {
            $pids -contains $_.OwningProcess -and $_.RemoteAddress -ne "127.0.0.1" -and $_.RemoteAddress -ne "::1"
        }
        return ($conns | Measure-Object).Count
    } catch {
        # Fallback netstat
        $count = 0
        try {
            $lines = netstat -ano | Select-String "ESTABLISHED"
            foreach ($line in $lines) {
                $parts = ($line.ToString().Trim() -split '\s+')
                if ($parts.Count -ge 5) {
                    $pidVal = [int]$parts[4]
                    $remote = $parts[2]
                    if ($pids -contains $pidVal -and -not $remote.StartsWith("127.0.0.1:") -and -not $remote.StartsWith("[::1]:")) {
                        $count++
                    }
                }
            }
        } catch {}
        return $count
    }
}

function Do-EarnAppSoftRestart([string]$exePath, [string]$reason) {
    Write-RestarterLog "[RESTART] Memicu restart EarnApp ($reason)..."
    
    # 1. Hentikan paksa proses EarnApp
    Stop-Process -Name "*earnapp*" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    
    # 2. Flush DNS & socket cache
    try {
        & ipconfig /flushdns | Out-Null
        Write-RestarterLog "[NETWORK] DNS cache berhasil di-flush."
    } catch {}
    
    # 3. Jalankan kembali EarnApp
    if ($exePath -and (Test-Path $exePath)) {
        Start-Process -FilePath $exePath -WindowStyle Minimized -ErrorAction SilentlyContinue
        Write-RestarterLog "[SUCCESS] EarnApp berhasil dijalankan kembali dari: $exePath"
    } else {
        Write-RestarterLog "[WARN] Path EarnApp tidak ditemukan, mencari kembali..."
        $newPath = Find-EarnAppExe
        if ($newPath) {
            Start-Process -FilePath $newPath -WindowStyle Minimized -ErrorAction SilentlyContinue
            Write-RestarterLog "[SUCCESS] EarnApp dijalankan dari: $newPath"
        } else {
            Write-RestarterLog "[ERROR] Gagal menemukan file executable EarnApp!"
        }
    }
}

# --- Inisialisasi ---
$eaPath = Find-EarnAppExe
Write-RestarterLog "=========================================================="
Write-RestarterLog "EarnApp Restarter aktif (PID: $PID)."
Write-RestarterLog "Path EarnApp: $(if ($eaPath) { $eaPath } else { 'Mencari...' })"
Write-RestarterLog "Aturan: Refresh rutin tiap 6 jam | Auto-restart jika stream <= 4 selama 20 menit"
Write-RestarterLog "=========================================================="

$lastRestartTime = Get-Date
$lowStreamMinutes = 0
$warmupUntil = (Get-Date).AddMinutes(5) # 5 menit pertama setelah start
$loopCounter = 0

while ($true) {
    Start-Sleep -Seconds 60
    $loopCounter++
    
    # Perbarui path jika belum ada
    if (-not $eaPath -or -not (Test-Path $eaPath)) {
        $eaPath = Find-EarnAppExe
    }

    $now = Get-Date
    $hoursSinceRestart = ($now - $lastRestartTime).TotalHours

    # 1. Cek Jadwal Rutin 6 Jam
    if ($hoursSinceRestart -ge 6.0) {
        Do-EarnAppSoftRestart -exePath $eaPath -reason "Rutin 6 Jam ($([Math]::Round($hoursSinceRestart, 1)) jam sejak restart terakhir)"
        $lastRestartTime = Get-Date
        $lowStreamMinutes = 0
        $warmupUntil = (Get-Date).AddMinutes(5)
        continue
    }

    # 2. Cek Masa Pemanasan (Warmup Grace Period 5 Menit setelah restart)
    if ($now -lt $warmupUntil) {
        $remainSec = [Math]::Floor(($warmupUntil - $now).TotalSeconds)
        if ($loopCounter % 2 -eq 0) {
            Write-RestarterLog "[WARMUP] EarnApp masa pemanasan (${remainSec}s tersisa). Menunggu koneksi terbentuk..."
        }
        $lowStreamMinutes = 0
        continue
    }

    # 3. Hitung Jumlah Stream Aktif
    $streams = Get-ActiveStreams
    $hoursLeft = [Math]::Round(6.0 - $hoursSinceRestart, 1)

    # 4. Logika Stuck Stream (<= 4 selama 20 menit)
    if ($streams -le 4) {
        $lowStreamMinutes++
        Write-RestarterLog "[LOW-STREAM] Stream: $streams (<= 4) selama $lowStreamMinutes / 20 menit. (Restart rutin: ${hoursLeft}j lagi)"

        if ($lowStreamMinutes -ge 20) {
            Write-RestarterLog "[STUCK-TRIGGER] Stream stuck di $streams (<= 4) selama $lowStreamMinutes menit! Me-restart EarnApp..."
            Do-EarnAppSoftRestart -exePath $eaPath -reason "Stream stuck di $streams selama 20 menit"
            $lastRestartTime = Get-Date
            $lowStreamMinutes = 0
            $warmupUntil = (Get-Date).AddMinutes(5)
            continue
        }
    } else {
        # Stream sehat (> 4)
        if ($lowStreamMinutes -gt 0) {
            Write-RestarterLog "[RECOVERED] Stream pulih kembali: $streams (> 4). Timer stuck direset ke 0."
        }
        $lowStreamMinutes = 0

        # Log heartbeat setiap 15 menit agar log tidak terlalu penuh
        if ($loopCounter % 15 -eq 0) {
            Write-RestarterLog "[HEALTHY] Stream: $streams aktif | Status normal | Restart rutin berikutnya dalam ${hoursLeft} jam."
        }
    }

    # Update state file untuk monitoring
    @{
        LastCheck = (Get-Date).ToString("o")
        LastRestart = $lastRestartTime.ToString("o")
        Streams = $streams
        LowStreamMinutes = $lowStreamMinutes
        NextRoutineRestartHours = $hoursLeft
    } | ConvertTo-Json | Set-Content -Path $stateFile -Force
}
