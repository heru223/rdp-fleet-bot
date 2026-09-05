# 🖥️ EarnApp Windows RDP Fleet Bot & Automation

Toolkit otomatisasi, optimasi 24/7, dan Bot Telegram Master untuk mengelola armada **Windows RDP EarnApp** secara **100% Headless (Tanpa Perlu Masuk Layar RDP)**.

---

## 🚀 Fitur Utama

1. **⚡ Headless Auto-Setup dari Telegram:**
   - Cukup ketik `/add <ip> <password> [folder]` di bot Telegram, sistem akan otomatis login via SSH, install EarnApp, whitelist Defender, dan kirim link klaim.
   - **Auto-Naming Otomatis Sesuai Folder:** Jika memilih folder `nayla`, worker otomatis dinamai `nayla-1`, `nayla-2`, `nayla-3`, dst.

2. **🎮 Kontrol Penuh dari Telegram (Tanpa Buka GUI RDP):**
   - **Reboot RDP:** Cukup klik tombol `[🔄 Reboot]` atau ketik `/reboot <nama>` untuk restart Windows RDP jika lag/berat.
   - **Restart EarnApp:** Perintah `/restart <nama>` untuk refresh proses EarnApp jika stream traffic macet.
   - **Interactive Multi-Folder Dashboard:** Pisahkan RDP berdasarkan grup (misal: 📁 `nayla`, 📁 `singapore`, 📁 `usa`).
   - **1-Click Claim Button:** Link klaim `https://earnapp.com/r/sdk-node-...` langsung dikirim via tombol interaktif Telegram.

3. **🛡️ Anti-Virus & Windows Defender Bypass Otomatis:**
   - Mematikan proteksi PUA (Potentially Unwanted Application) yang sering memblokir EarnApp.
   - Otomatis memasukkan folder dan file `earnapp.exe` ke whitelist exclusion Defender.

4. **🔄 24/7 Keep-Alive & Auto-Reboot Rutin:**
   - **Anti-Sleep:** Power plan High Performance (layar & disk tidak pernah tidur).
   - **RDP Keep-Alive (`Disconnect-RDP.bat`):** Sesi RDP dialihkan ke konsol lokal saat ditutup, sehingga aplikasi EarnApp tetap hidup dan aktif menghasilkan stream di background tanpa terkunci.
   - **Auto-Reboot 24 Jam:** Task Scheduler harian jam 04:00 AM untuk membersihkan cache RAM.

---

## 📱 Cara Penggunaan di Bot Telegram (`@RdpfleetBot`)

### 1. Tambah RDP Otomatis (Tanpa Buka Layar RDP)
Kirim perintah ini di chat bot:
```text
/add <ip> <password> [folder]
```
*Contoh:*
```text
/add 104.238.150.12 RahasiaPassword nayla
```
*Hasil:*
Bot akan otomatis menamai worker sebagai **nayla-1**, menginstall EarnApp, whitelist antivirus, dan membalas dengan link klaim akun dalam ~30 detik!

---

### 2. Jika Port Remote RDP Ditutup oleh Provider (Setup 1-Klik 5 Detik Sekali Saja)
Jika provider RDP mengunci semua port kecuali 3389:
1. Buka RDP sekali saja via Remote Desktop Connection.
2. Buka **PowerShell (Run as Administrator)**, lalu paste perintah 1-baris ini:
```powershell
irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex
```
*Script ini otomatis menginstall **OpenSSH Server** dan membuka port 22 di Firewall Windows RDP. Setelah langkah 1x ini (cuma butuh 5 detik), **UNTUK SETERUSNYA RDP INI 100% BISA DIKONTROL DARI BOT TELEGRAM** tanpa perlu login layar lagi!*

---

## 🛠️ Setup di VPS Master Linux

Di VPS Master Anda, jalankan perintah berikut untuk mengaktifkan bot RDP secara terpisah (bebas bentrok dengan bot Linux VPS):

```bash
# 1. Clone repository
git clone https://github.com/heru223/rdp-fleet-bot.git /root/rdp-fleet-bot
cd /root/rdp-fleet-bot

# 2. Install dependensi remote SSH
apt-get update && apt-get install -y sshpass openssh-client

# 3. Buat systemd service rdp_bot.service
cat << 'EOF' > /etc/systemd/system/rdp_bot.service
[Unit]
Description=EarnApp Windows RDP Fleet Telegram Controller
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/rdp-fleet-bot
ExecStart=/usr/bin/python3 /root/rdp-fleet-bot/rdp_master_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 4. Aktifkan dan jalankan service
systemctl daemon-reload
systemctl enable rdp_bot.service
systemctl restart rdp_bot.service
systemctl status rdp_bot.service --no-pager
```

Buka bot Telegram Anda di **[@RdpfleetBot](https://t.me/RdpfleetBot)** dan kirim perintah `/start`!
