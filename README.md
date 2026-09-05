# 🖥️ EarnApp Windows RDP Fleet Bot (Outbound Stealth Architecture)

Toolkit otomatisasi, optimasi 24/7, dan Bot Telegram Master untuk mengelola armada **Windows RDP EarnApp** dengan arsitektur **Outbound Stealth Agent (0 Port Terbuka / 100% Aman & Anti-Curiga dari Penyedia RDP)**.

---

## 🔒 Kenapa Arsitektur Ini 100% Aman & Tidak Akan Diketahui Penyedia RDP?

1. **NOL Port Masuk (0 Inbound Port):**
   - Port 22 (SSH) dan port lain **tetap MATI TOTAL**.
   - Di mata sistem scanner penyedia RDP, firewall Windows RDP Anda masih 100% standar pabrik.
2. **Trafik Keluar Seperti Browsing Biasa (Outbound Only):**
   - RDP hanya mengirim sinyal keluar ke Master VPS tiap 15 detik (persis seperti aplikasi biasa membuka web atau sinkronisasi OneDrive/EarnApp).
3. **Beban CPU & RAM 0.01%:**
   - Tidak ada proses berat, sangat hemat daya dan tidak memicu alarm pemakaian CPU.
4. **Disamarkan Menjadi Task Windows Resmi:**
   - Task Scheduler berjalan di background dengan nama `WindowsSystemHealthMonitor`.

---

## 🚀 Fitur Utama

1. **🎮 Kontrol Penuh dari Telegram ([@RdpfleetBot](https://t.me/RdpfleetBot)):**
   - **Reboot RDP Remote:** Cukup klik tombol `[🔄 Reboot]` atau ketik `/reboot <nama>` untuk restart Windows RDP jika lag/berat (dieksekusi dalam ~15 detik).
   - **Restart EarnApp:** Perintah `/restart <nama>` untuk me-restart proses EarnApp jika traffic macet.
   - **Interactive Multi-Folder Dashboard:** Pisahkan RDP berdasarkan folder (misal: 📁 `nayla`, 📁 `singapore`, 📁 `usa`).
   - **Auto-Naming Urut:** Jika memilih folder `nayla`, worker otomatis dinamai `nayla-1`, `nayla-2`, `nayla-3`, dst.
   - **1-Click Claim Button:** Link klaim `https://earnapp.com/r/sdk-node-...` langsung dikirim via tombol interaktif Telegram.

2. **🛡️ Anti-Virus & Windows Defender Bypass Otomatis:**
   - Mematikan proteksi PUA (Potentially Unwanted Application) yang memblokir EarnApp.
   - Otomatis memasukkan folder dan file `earnapp.exe` ke whitelist exclusion Defender.

3. **🔄 24/7 Keep-Alive & Auto-Reboot Rutin:**
   - **Anti-Sleep:** Power plan High Performance (layar & disk tidak pernah tidur).
   - **RDP Keep-Alive (`Disconnect-RDP.bat`):** Sesi RDP dialihkan ke konsol lokal saat ditutup, sehingga aplikasi EarnApp tetap aktif menghasilkan stream di background tanpa terkunci.
   - **Auto-Reboot 24 Jam:** Task Scheduler harian jam 04:00 AM untuk membersihkan cache RAM.

---

## 📱 Cara Menghubungkan RDP Baru (Hanya Butuh 5 Detik Sekali Saja)

1. Buka RDP Anda (gunakan ukuran kecil `mstsc /v:<ip> /w:1024 /h:768` agar enteng dan tidak lemot).
2. Buka **PowerShell (Run as Administrator)**.
3. Buka bot Telegram [@RdpfleetBot](https://t.me/RdpfleetBot) ➜ klik tombol **`[➕ Tambah / Setup RDP]`** (atau buka folder lalu klik **`[➕ Tambah ke folder]`**).
4. Bot akan memberikan 1 baris perintah. Copy dan paste ke PowerShell RDP lalu tekan Enter:
   ```powershell
   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1))) -MasterIP <IP_VPS_MASTER> -Folder <NAMA_FOLDER>
   ```
5. **Langsung tutup RDP!** Anda tidak perlu menunggu di layarnya.
6. Dalam hitungan detik, RDP akan otomatis terdaftar dan link klaim EarnApp langsung terkirim ke Telegram Anda!

---

## 🛠️ Update Service di VPS Master Linux

Di VPS Master Anda, jalankan perintah berikut untuk mengaktifkan update terbaru:

```bash
cd /root/rdp-fleet-bot
git pull

# Pastikan port 9090 diizinkan jika menggunakan ufw
ufw allow 9090/tcp 2>/dev/null

systemctl restart rdp_bot.service
systemctl status rdp_bot.service --no-pager
```
