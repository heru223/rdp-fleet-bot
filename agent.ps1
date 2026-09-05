# =========================================================================
#  EARNAPP WINDOWS RDP STEALTH OUTBOUND AGENT
#  Repository: https://github.com/heru223/rdp-fleet-bot
# =========================================================================

$ErrorActionPreference = "SilentlyContinue"
$configPath = "C:\ProgramData\WinNetworkMonitor\config.json"
if (-not (Test-Path $configPath)) { exit }

# Pastikan hanya 1 instance agent yang berjalan
$myPid = $PID
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*WinNetworkMonitor\agent.ps1*" -and $_.ProcessId -ne $myPid }
if ($procs) { exit }

while ($true) {
    try {
        if (Test-Path $configPath) {
            $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
            if ($cfg.MasterIP -and $cfg.MasterIP -ne "") {
                $masterUrl = "http://$($cfg.MasterIP):$($cfg.MasterPort)/heartbeat"
                $resultUrl = "http://$($cfg.MasterIP):$($cfg.MasterPort)/command_result"

                # 1. Ambil info RAM
                $os = Get-CimInstance Win32_OperatingSystem
                $totMb = [math]::Round($os.TotalVisibleMemorySize / 1024)
                $frMb = [math]::Round($os.FreePhysicalMemory / 1024)
                $usMb = $totMb - $frMb
                $pct = if ($totMb -gt 0) { [math]::Round(($usMb / $totMb) * 100) } else { 0 }
                $ramStr = "$usMb MB / $totMb MB ($pct`%)"

                # 2. Status EarnApp
                $eaProc = Get-Process -Name "*earnapp*" -ErrorAction SilentlyContinue
                $eaStatus = if ($eaProc) { "running" } else { "stopped" }

                # 3. Uptime
                $bootTime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
                $uptimeHours = [math]::Round((((Get-Date) - $bootTime).TotalHours), 1)

                # 4. Ambil UUID jika belum ada di config
                $uuid = $cfg.NodeID
                if ([string]::IsNullOrEmpty($uuid) -or $uuid -eq "-") {
                    $checkPaths = @(
                        "C:\Program Files (x86)\EarnApp\uuid",
                        "C:\Program Files\EarnApp\uuid",
                        "$env:ProgramData\EarnApp\uuid",
                        "$env:LOCALAPPDATA\EarnApp\uuid"
                    )
                    foreach ($cp in $checkPaths) {
                        if (Test-Path $cp) {
                            $txt = (Get-Content $cp -Raw).Trim()
                            if ($txt -match "sdk-node-") {
                                $uuid = $txt
                                $cfg.NodeID = $uuid
                                $cfg | ConvertTo-Json -Indent 2 | Set-Content -Path $configPath -Force
                                break
                            }
                        }
                    }
                }

                # 5. Kirim Heartbeat ke Master VPS
                $payload = @{
                    ip = $cfg.PublicIP
                    name = $cfg.WorkerName
                    folder = $cfg.Folder
                    uuid = $uuid
                    ram = $ramStr
                    status = $eaStatus
                    uptime = "$uptimeHours jam"
                } | ConvertTo-Json -Compress

                $resp = Invoke-RestMethod -Uri $masterUrl -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 10

                # Jika Master menamai ulang worker secara otomatis
                if ($resp -and $resp.assigned_name -and $resp.assigned_name -ne $cfg.WorkerName) {
                    $cfg.WorkerName = $resp.assigned_name
                    $cfg | ConvertTo-Json -Indent 2 | Set-Content -Path $configPath -Force
                }

                # 6. Eksekusi Perintah Remote jika ada
                if ($resp -and $resp.command) {
                    $cmd = $resp.command
                    $cmdId = $resp.cmd_id

                    if ($cmd -eq "reboot") {
                        $resPayload = @{ ip = $cfg.PublicIP; name = $cfg.WorkerName; cmd = "reboot"; status = "rebooting" } | ConvertTo-Json -Compress
                        Invoke-RestMethod -Uri $resultUrl -Method Post -Body $resPayload -ContentType "application/json" -TimeoutSec 5 -ErrorAction SilentlyContinue
                        Start-Sleep -Seconds 2
                        shutdown.exe /r /t 5 /f /c "Telegram Master Remote Reboot"
                    } elseif ($cmd -eq "restart_earnapp") {
                        Stop-Process -Name "*earnapp*" -Force -ErrorAction SilentlyContinue
                        Start-Sleep -Seconds 3
                        if (Test-Path "C:\Program Files (x86)\EarnApp\earnapp.exe") {
                            Start-Process "C:\Program Files (x86)\EarnApp\earnapp.exe" -ErrorAction SilentlyContinue
                        } elseif (Test-Path "C:\Program Files\EarnApp\earnapp.exe") {
                            Start-Process "C:\Program Files\EarnApp\earnapp.exe" -ErrorAction SilentlyContinue
                        }
                        $resPayload = @{ ip = $cfg.PublicIP; name = $cfg.WorkerName; cmd = "restart_earnapp"; status = "restarted" } | ConvertTo-Json -Compress
                        Invoke-RestMethod -Uri $resultUrl -Method Post -Body $resPayload -ContentType "application/json" -TimeoutSec 5 -ErrorAction SilentlyContinue
                    }
                }
            }
        }
    } catch {}
    Start-Sleep -Seconds 15
}
