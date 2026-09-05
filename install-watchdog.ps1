# =========================================================================
#  INSTALLER: EARNAPP AUTONOMOUS WATCHDOG FOR WINDOWS RDP
#  - Otomatis pasang Task Scheduler (berjalan tiap 2 menit sebagai SYSTEM)
#  - Reboot rutin tiap 6 jam (360 menit)
#  - Auto-reboot jika EarnApp streams <= 4 selama 20 menit
#  - Startup grace period 20 menit (mencegah reboot loop saat baru nyala)
#  - Shortcut cek status di Desktop
#  - Auto-reboot pertama kali setelah selesai pasang
# =========================================================================

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " [*] MEMASANG EARNAPP AUTONOMOUS WATCHDOG" -ForegroundColor Green
Write-Host "     - Auto-reboot tiap 6 jam" -ForegroundColor White
Write-Host "     - Auto-reboot jika stream <= 4 selama 20 menit" -ForegroundColor White
Write-Host "     - Mandiri & Ringan (Tanpa Bot / Port Terbuka)" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Pastikan Hak Akses Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] Script ini membutuhkan hak Administrator." -ForegroundColor Yellow
    Write-Host "[*] Membuka kembali sebagai Administrator..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# 2. Buat Direktori C:\EarnAppWatchdog
$dir = "C:\EarnAppWatchdog"
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# 3. Buat Script watchdog.ps1
$watchdogScriptPath = "$dir\watchdog.ps1"
$watchdogCode = @'
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
    Write-WatchdogLog "[REBOOT-6H] Uptime telah mencapai $uptimeHours jam ($uptimeMinutes min >= 360 min). Menjalankan auto-reboot rutin 6 jam..."
    if (Test-Path $stateFile) { Remove-Item $stateFile -Force -ErrorAction SilentlyContinue }
    & shutdown.exe /r /t 15 /f /c "EarnApp Watchdog: Routine 6-hour reboot"
    exit
}

# --- 3. Baca State File ---
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
        $state.LowStreamStart = (Get-Date).ToString("o")
        Write-WatchdogLog "[LOW-STREAM] Streams: $streams (<= 4). Timer stuck dimulai pada $($state.LowStreamStart)."
    } else {
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
    if (-not [string]::IsNullOrWhiteSpace($state.LowStreamStart)) {
        Write-WatchdogLog "[RECOVERED] Streams kembali normal: $streams (> 4). Timer stuck direset ke 0."
    } else {
        Write-WatchdogLog "[OK] Normal | Streams: $streams | Uptime: $uptimeHours j / 6 j"
    }
    $state.LowStreamStart = ""
}

$state | ConvertTo-Json | Set-Content -Path $stateFile -Force
'@

Set-Content -Path $watchdogScriptPath -Value $watchdogCode -Encoding ASCII -Force
Write-Host "  [OK] Script watchdog tersimpan di $watchdogScriptPath" -ForegroundColor Green

# 4. Buat runner batch run.cmd
$runCmdPath = "$dir\run.cmd"
$runCmdContent = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdogScriptPath`"`r`n"
Set-Content -Path $runCmdPath -Value $runCmdContent -Encoding ASCII -Force

# 5. Buat tool Cek Status (status.cmd) di C:\EarnAppWatchdog (Tanpa Icon Desktop)
$statusCmdPath = "$dir\status.cmd"
$statusContent = @"
@echo off
title EarnApp Watchdog Status
echo ==========================================================
echo        STATUS EARNAPP AUTONOMOUS WATCHDOG
echo ==========================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$os = Get-CimInstance Win32_OperatingSystem; $upMin = [Math]::Floor(((Get-Date) - $os.LastBootUpTime).TotalMinutes); $upH = [Math]::Round($upMin/60, 1); $nextH = [Math]::Round((360 - $upMin)/60, 1); Write-Host ' [Uptime Sistem] :' $upH 'jam (' $upMin 'menit)'; Write-Host ' [Reboot 6 Jam] :' $nextH 'jam lagi'; $ea = Get-Process -Name '*earnapp*' -ErrorAction SilentlyContinue; if ($ea) { $pids = $ea.Id; $conns = (Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object { $pids -contains $_.OwningProcess -and $_.RemoteAddress -ne '127.0.0.1' -and $_.RemoteAddress -ne '::1' } | Measure-Object).Count; Write-Host ' [EarnApp Status] : RUNNING (PID: ' ($pids -join ',') ')' -ForegroundColor Green; Write-Host ' [Active Streams]:' $conns -ForegroundColor Cyan } else { Write-Host ' [EarnApp Status] : TIDAK BERJALAN' -ForegroundColor Red }"
echo.
echo Log 10 Pemeriksaan Terakhir:
echo ----------------------------------------------------------
if exist "C:\EarnAppWatchdog\watchdog.log" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Content 'C:\EarnAppWatchdog\watchdog.log' -Tail 10"
) else (
    echo Belum ada catatan log.
)
echo ----------------------------------------------------------
echo.
pause
"@
Set-Content -Path $statusCmdPath -Value $statusContent -Encoding ASCII -Force

# Bersihkan icon dari Desktop agar tampilan bersih total
Remove-Item "C:\Users\*\Desktop\Cek-EarnApp-Status.bat" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Users\Public\Desktop\Cek-EarnApp-Status.bat" -Force -ErrorAction SilentlyContinue

# 6. Registrasi Task Scheduler (Setiap 2 Menit & Saat Startup)
Write-Host "  [*] Mendaftarkan Task Scheduler (Jalan tiap 2 menit sebagai SYSTEM)..." -ForegroundColor Cyan

# Hapus task lama jika ada
schtasks.exe /delete /tn "EarnApp-Watchdog" /f 2>$null | Out-Null
schtasks.exe /delete /tn "EarnAppWatchdog" /f 2>$null | Out-Null

$taskRegistered = $false
try {
    $act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$runCmdPath`""
    $trg1 = New-ScheduledTaskTrigger -AtStartup
    $trg2 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration ([TimeSpan]::MaxValue)
    $prn = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $stg = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances Parallel -ExecutionTimeLimit (New-TimeSpan -Days 0)
    Register-ScheduledTask -TaskName "EarnApp-Watchdog" -Action $act -Trigger @($trg1, $trg2) -Principal $prn -Settings $stg -Force -ErrorAction Stop | Out-Null
    $taskRegistered = $true
    Write-Host "  [OK] Task Scheduler 'EarnApp-Watchdog' berhasil didaftarkan via PowerShell." -ForegroundColor Green
} catch {
    # Fallback ke schtasks.exe jika PowerShell cmdlet gagal
    schtasks.exe /create /tn "EarnApp-Watchdog" /tr "cmd.exe /c `"$runCmdPath`"" /sc minute /mo 2 /ru "SYSTEM" /rl HIGHEST /f 2>$null | Out-Null
    $taskRegistered = $true
    Write-Host "  [OK] Task Scheduler 'EarnApp-Watchdog' berhasil didaftarkan via schtasks.exe." -ForegroundColor Green
}

# 7. Pastikan EarnApp ada di Startup Folder All Users
$startupDir = "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
$earnappExeFound = $null
$searchPaths = @(
    "C:\Program Files (x86)\EarnApp\earnapp.exe",
    "C:\Program Files\EarnApp\earnapp.exe",
    "$env:LOCALAPPDATA\Programs\EarnApp\earnapp.exe",
    "$env:APPDATA\EarnApp\earnapp.exe",
    "C:\ProgramData\EarnApp\earnapp.exe"
)
foreach ($sp in $searchPaths) {
    if (Test-Path $sp) {
        $earnappExeFound = $sp
        break
    }
}
if ($earnappExeFound -and (Test-Path $startupDir)) {
    $startEarnappBat = "$startupDir\Start-EarnApp.bat"
    Set-Content -Path $startEarnappBat -Value "start `"`" `"$earnappExeFound`"" -Encoding ASCII -Force
    Write-Host "  [OK] EarnApp Startup terdaftar di All Users Startup ($earnappExeFound)." -ForegroundColor Green
}

# Jalankan 1 kali pengecekan sekarang
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $watchdogScriptPath | Out-Null

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host " [SUKSES] INSTALASI WATCHDOG SELESAI!" -ForegroundColor Green
Write-Host " - Auto-reboot 6 jam          : AKTIF" -ForegroundColor White
Write-Host " - Watchdog stream <= 4 (20m) : AKTIF" -ForegroundColor White
Write-Host " - Pengecekan                 : Tiap 2 Menit (Background SYSTEM)" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "`n[!] Sesuai permintaan, RDP akan REBOOT SEKARANG dalam 10 detik..." -ForegroundColor Yellow
Write-Host "    (Silakan tunggu 1-2 menit lalu login kembali ke RDP)" -ForegroundColor Yellow

for ($i = 10; $i -gt 0; $i--) {
    Write-Host "    Reboot dalam $i detik...`r" -NoNewline -ForegroundColor Cyan
    Start-Sleep -Seconds 1
}

Write-Host "`n[*] REBOOTING SEKARANG..." -ForegroundColor Red
& shutdown.exe /r /t 2 /f /c "EarnApp Watchdog: Setup selesai, initial reboot"
