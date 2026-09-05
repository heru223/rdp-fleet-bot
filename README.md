# 🖥️ EarnApp Windows RDP Fleet Bot & Automation

Toolkit otomatisasi, optimasi 24/7, dan Bot Telegram Master untuk mengelola armada **Windows RDP EarnApp**.

---

## 🚀 Fitur Utama

1. **⚡ 1-Click Setup & Optimizer di Windows RDP:**
   - Deteksi otomatis apakah EarnApp sudah berjalan (tidak mereset/menimpa data yang ada).
   - Ekstrak Node ID unik & langsung kirim link klaim ke Bot Telegram.
   - **Anti-Sleep:** Power plan High Performance (layar & disk tidak pernah tidur).
   - **RDP Keep-Alive (`Disconnect-RDP.bat`):** Sesi RDP dialihkan ke konsol lokal saat ditutup, sehingga aplikasi EarnApp tetap hidup dan aktif menghasilkan stream di background tanpa terkunci.
   - **Auto-Reboot 24 Jam Rutin:** Task Scheduler untuk restart Windows otomatis tiap 24 jam sekali guna menyegarkan memori RAM RDP.
2. **🤖 Dedicated Telegram Bot Controller (`@RdpfleetBot`):**
   - Terpisah dari bot Linux VPS untuk kenyamanan manajemen armada.
   - Dashboard multi-folder (misal: 📁 `RDP`, 📁 `Singapore`, 📁 `USA`).
   - Tombol 1-klik klaim akun EarnApp via Telegram.
   - Daftar seluruh Node ID & Claim URL.

---

## 💻 Cara Pakai di Windows RDP (1-Klik Saja)

Buka **PowerShell (Run as Administrator)** di RDP Anda, lalu paste dan tekan Enter:

```powershell
irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex
```

*Sistem akan otomatis mengoptimasi RDP, membaca status EarnApp, dan mengirimkan detailnya langsung ke Telegram Anda!*

---

## 🛠️ Cara Menjalankan Master Bot di VPS Master (Bebas Bentrok)

Di VPS Master Anda, jalankan perintah berikut untuk menginstall bot RDP secara terpisah:

```bash
# 1. Clone repository ke direktori khusus RDP
git clone https://github.com/heru223/rdp-fleet-bot.git /root/rdp-fleet-bot
cd /root/rdp-fleet-bot

# 2. Buat systemd service rdp_bot.service
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

# 3. Aktifkan dan jalankan service
systemctl daemon-reload
systemctl enable rdp_bot.service
systemctl restart rdp_bot.service
systemctl status rdp_bot.service --no-pager
```

Buka bot Telegram Anda di **[@RdpfleetBot](https://t.me/RdpfleetBot)** dan kirim perintah `/start`!

---

## 🛡️ Solusi Anti-Virus / Windows Defender (False Positive)

EarnApp sering dideteksi sebagai **PUA (Potentially Unwanted Application)** atau **Proxyware** oleh Windows Defender.

* **Otomatis:** Script `setup.ps1` sudah otomatis mematikan proteksi PUA dan menambahkan whitelist path & proses EarnApp.
* **Manual / Khusus Antivirus Saja:** Jika di RDP lama Anda EarnApp terblokir atau terhapus oleh Defender, cukup buka PowerShell (Admin) dan jalankan:

```powershell
irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/Bypass-Antivirus.ps1 | iex
```
