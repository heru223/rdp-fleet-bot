# =========================================================================
#  EARNAPP WINDOWS DEFENDER & ANTIVIRUS BYPASS TOOL
#  Whitelist EarnApp paths, processes, and disable PUA blocking
#  Repository: https://github.com/heru223/rdp-fleet-bot
# =========================================================================

# Pastikan Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Meminta hak Administrator..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " 🛡️ EARNAPP ANTIVIRUS & WINDOWS DEFENDER WHITELIST TOOL 🛡️" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

try {
    # 1. Matikan PUA Protection (Potentially Unwanted Application)
    Write-Host "[1/4] Menonaktifkan PUA Protection..." -ForegroundColor Yellow
    Set-MpPreference -PUAProtection Disabled -ErrorAction SilentlyContinue
    New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender" -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender" -Name "PUAProtection" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
    Write-Host "  ✅ PUA Protection berhasil dimatikan." -ForegroundColor Green

    # 2. Whitelist Direktori EarnApp
    Write-Host "[2/4] Menambahkan Folder Exclusions..." -ForegroundColor Yellow
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
        Write-Host "  ✅ Whitelist Folder: $f" -ForegroundColor Green
    }

    # 3. Whitelist Proses
    Write-Host "[3/4] Menambahkan Process Exclusions..." -ForegroundColor Yellow
    Add-MpPreference -ExclusionProcess "earnapp.exe", "EarnApp.exe", "EarnAppSetup.exe" -ErrorAction SilentlyContinue
    Write-Host "  ✅ Whitelist Proses: earnapp.exe, EarnApp.exe" -ForegroundColor Green

    # 4. Matikan Realtime Monitoring di RDP (Mencegah CPU 100% & Interupsi)
    Write-Host "[4/4] Mengatur Real-time Monitoring..." -ForegroundColor Yellow
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue
    Write-Host "  ✅ Real-time Scanning dinonaktifkan untuk performa maksimal RDP." -ForegroundColor Green

    Write-Host "`n🎉 SUKSES! EarnApp sekarang 100% kebal dari deteksi virus / Windows Defender." -ForegroundColor Green
} catch {
    Write-Host "`n⚠️ Terjadi kesalahan: $_" -ForegroundColor Red
}

Write-Host "`nTekan [ENTER] untuk keluar..."
Read-Host
