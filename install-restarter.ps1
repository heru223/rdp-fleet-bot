# =========================================================================
#  INSTALLER: EARNAPP SOFT-RESTARTER & STREAM WATCHDOG (NOL REBOOT OS)
#  - Otomatis restart EarnApp tiap 6 jam
#  - Otomatis restart EarnApp jika stream <= 4 selama 20 menit
#  - Flush DNS & refresh koneksi
#  - 100% BEBAS REBOOT OS (RDP aman 24/7, tidak akan mati, tidak perlu buka panel)
#  - Desktop 100% bersih tanpa icon/shortcut
# =========================================================================

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " [*] MEMASANG EARNAPP SOFT-RESTARTER & STREAM WATCHDOG" -ForegroundColor Green
Write-Host "     - Auto-restart EarnApp tiap 6 jam" -ForegroundColor White
Write-Host "     - Auto-restart EarnApp jika stream <= 4 (20 menit)" -ForegroundColor White
Write-Host "     - 100% TANPA REBOOT OS (RDP aman, tidak perlu buka panel)" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Bersihkan semua task reboot lama & icon desktop
Write-Host "`n[1/4] Membersihkan sisa task lama & merapikan sistem..." -ForegroundColor Cyan
schtasks.exe /delete /tn "EarnApp-Watchdog" /f 2>$null | Out-Null
schtasks.exe /delete /tn "EarnAppWatchdog" /f 2>$null | Out-Null
schtasks.exe /delete /tn "WindowsSystemHealthMonitor" /f 2>$null | Out-Null
schtasks.exe /delete /tn "EarnApp-Daily-Reboot" /f 2>$null | Out-Null
Remove-Item "C:\EarnAppWatchdog" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Users\*\Desktop\Cek-EarnApp-Status.bat" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Users\Public\Desktop\Cek-EarnApp-Status.bat" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Users\*\Desktop\Disconnect-RDP.bat" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Users\Public\Desktop\Disconnect-RDP.bat" -Force -ErrorAction SilentlyContinue
Write-Host "  [OK] Pembersihan selesai. Desktop bersih total." -ForegroundColor Green

# 2. Buat folder C:\EarnAppRestarter
$dir = "C:\EarnAppRestarter"
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# 3. Buat script restarter.ps1 (Self-Contained)
Write-Host "`n[2/4] Menyiapkan script restarter..." -ForegroundColor Cyan
$restarterScriptPath = "$dir\restarter.ps1"
$restarterCode = @'
$ErrorActionPreference = "SilentlyContinue"

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
        if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 1048576)) {
            $lines = Get-Content -Path $logFile -Tail 500
            Set-Content -Path $logFile -Value $lines -Force
        }
    } catch {}
    Write-Host $entry
}

function Find-EarnAppExe {
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
    
    Stop-Process -Name "*earnapp*" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    
    try {
        & ipconfig /flushdns | Out-Null
        Write-RestarterLog "[NETWORK] DNS cache berhasil di-flush."
    } catch {}
    
    if ($exePath -and (Test-Path $exePath)) {
        Start-Process -FilePath $exePath -WindowStyle Minimized -ErrorAction SilentlyContinue
        Write-RestarterLog "[SUCCESS] EarnApp berhasil dijalankan kembali dari: $exePath"
    } else {
        $newPath = Find-EarnAppExe
        if ($newPath) {
            Start-Process -FilePath $newPath -WindowStyle Minimized -ErrorAction SilentlyContinue
            Write-RestarterLog "[SUCCESS] EarnApp dijalankan dari: $newPath"
        } else {
            Write-RestarterLog "[ERROR] Gagal menemukan file executable EarnApp!"
        }
    }
}

$eaPath = Find-EarnAppExe
Write-RestarterLog "=========================================================="
Write-RestarterLog "EarnApp Restarter aktif (PID: $PID)."
Write-RestarterLog "Path EarnApp: $(if ($eaPath) { $eaPath } else { 'Mencari...' })"
Write-RestarterLog "Aturan: Refresh rutin tiap 6 jam | Auto-restart jika stream <= 4 selama 20 menit"
Write-RestarterLog "=========================================================="

$lastRestartTime = Get-Date
$lowStreamMinutes = 0
$warmupUntil = (Get-Date).AddMinutes(5)
$loopCounter = 0

while ($true) {
    Start-Sleep -Seconds 60
    $loopCounter++
    
    if (-not $eaPath -or -not (Test-Path $eaPath)) {
        $eaPath = Find-EarnAppExe
    }

    $now = Get-Date
    $hoursSinceRestart = ($now - $lastRestartTime).TotalHours

    if ($hoursSinceRestart -ge 6.0) {
        Do-EarnAppSoftRestart -exePath $eaPath -reason "Rutin 6 Jam ($([Math]::Round($hoursSinceRestart, 1)) jam sejak restart terakhir)"
        $lastRestartTime = Get-Date
        $lowStreamMinutes = 0
        $warmupUntil = (Get-Date).AddMinutes(5)
        continue
    }

    if ($now -lt $warmupUntil) {
        $remainSec = [Math]::Floor(($warmupUntil - $now).TotalSeconds)
        if ($loopCounter % 2 -eq 0) {
            Write-RestarterLog "[WARMUP] EarnApp masa pemanasan (${remainSec}s tersisa). Menunggu koneksi terbentuk..."
        }
        $lowStreamMinutes = 0
        continue
    }

    $streams = Get-ActiveStreams
    $hoursLeft = [Math]::Round(6.0 - $hoursSinceRestart, 1)

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
        if ($lowStreamMinutes -gt 0) {
            Write-RestarterLog "[RECOVERED] Stream pulih kembali: $streams (> 4). Timer stuck direset ke 0."
        }
        $lowStreamMinutes = 0

        if ($loopCounter % 15 -eq 0) {
            Write-RestarterLog "[HEALTHY] Stream: $streams aktif | Status normal | Restart rutin berikutnya dalam ${hoursLeft} jam."
        }
    }

    @{
        LastCheck = (Get-Date).ToString("o")
        LastRestart = $lastRestartTime.ToString("o")
        Streams = $streams
        LowStreamMinutes = $lowStreamMinutes
        NextRoutineRestartHours = $hoursLeft
    } | ConvertTo-Json | Set-Content -Path $stateFile -Force
}
'@

Set-Content -Path $restarterScriptPath -Value $restarterCode -Encoding ASCII -Force
Write-Host "  [OK] Script restarter tersimpan di $restarterScriptPath" -ForegroundColor Green

# 4. Buat runner batch & Daftarkan Auto-Start
Write-Host "`n[3/4] Mendaftarkan background restarter..." -ForegroundColor Cyan
$runCmdPath = "$dir\run.cmd"
$runCmdContent = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$restarterScriptPath`"`r`n"
Set-Content -Path $runCmdPath -Value $runCmdContent -Encoding ASCII -Force

# Startup folder All Users (agar selalu jalan otomatis jika mesin nyala/login)
$startupFolder = "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
if (Test-Path $startupFolder) {
    Set-Content -Path "$startupFolder\Start-EarnAppRestarter.cmd" -Value "call `"$runCmdPath`"" -Encoding ASCII -Force
}

# Hentikan proses restarter lama jika ada
Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "restarter\.ps1" } | Stop-Process -Force -ErrorAction SilentlyContinue

# 5. Lakukan Restart Pertama EarnApp untuk refresh koneksi sekarang
Write-Host "`n[4/4] Menjalankan Soft-Restart pertama untuk menyegarkan EarnApp..." -ForegroundColor Cyan
$eaProcs = Get-Process -Name "*earnapp*" -ErrorAction SilentlyContinue
$eaPath = $null
if ($eaProcs) {
    try { $eaPath = $eaProcs[0].MainModule.FileName } catch {}
}
if (-not $eaPath) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\EarnApp\earnapp.exe",
        "C:\Program Files (x86)\EarnApp\earnapp.exe",
        "C:\Program Files\EarnApp\earnapp.exe",
        "$env:APPDATA\EarnApp\earnapp.exe",
        "C:\ProgramData\EarnApp\earnapp.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $eaPath = $c; break }
    }
}

Stop-Process -Name "*earnapp*" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
ipconfig /flushdns | Out-Null

if ($eaPath -and (Test-Path $eaPath)) {
    Start-Process -FilePath $eaPath -WindowStyle Minimized -ErrorAction SilentlyContinue
    Write-Host "  [OK] EarnApp berhasil di-restart & koneksi di-refresh!" -ForegroundColor Green
} else {
    Write-Host "  [!] Silakan buka aplikasi EarnApp jika belum muncul." -ForegroundColor Yellow
}

# Jalankan restarter di background sekarang
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$restarterScriptPath`"" -WindowStyle Hidden

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host " [SUKSES] EARNAPP SOFT-RESTARTER TELAH AKTIF!" -ForegroundColor Green
Write-Host " - Refresh rutin tiap 6 jam    : AKTIF (Soft-restart EarnApp)" -ForegroundColor White
Write-Host " - Stuck stream <= 4 (20 menit): AKTIF (Soft-restart EarnApp)" -ForegroundColor White
Write-Host " - Status Reboot OS            : NONAKTIF (RDP Aman 24/7)" -ForegroundColor Green
Write-Host " - Status Desktop              : Bersih Total (Nol Icon)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "RDP kamu tetap online terus, tidak akan mati, dan tidak perlu buka panel!`n" -ForegroundColor Yellow
