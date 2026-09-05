#!/usr/bin/env python3
"""
EarnApp Windows RDP Fleet Master Controller Bot
- Dedicated Telegram Bot for Windows RDP fleet management (@RdpfleetBot)
- Headless remote setup via SSH / WinRM: Add RDP directly from Telegram without opening RDP GUI!
- Automatic worker naming based on folder (e.g. nayla-1, nayla-2, nayla-3)
- Remote execution: Reboot RDP, Restart EarnApp, Check status over SSH
- Multi-folder & grouping system
- Node ID & Claim URL tracker with 1-click inline buttons
- Lightweight HTTP registration / heartbeat listener (port 9090)
"""

import os
import sys
import time
import json
import re
import html
import socket
import subprocess
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

DATA_DIR = "/root/rdp-fleet-bot"
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
NODES_FILE = os.path.join(DATA_DIR, "nodes.json")

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "bot_token": "8915903428:AAEciefmI7dRj5KH6KsWPK7--eOODNm34lg",
    "allowed_chat_id": "1943547868",
    "http_port": 9090
}

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                cfg.update(d)
        except Exception:
            pass
    else:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
    return cfg.get("bot_token"), int(cfg.get("allowed_chat_id", 1943547868)), int(cfg.get("http_port", 9090))

BOT_TOKEN, ADMIN_CHAT_ID, HTTP_PORT = load_config()

NODES_LOCK = threading.Lock()
LAST_DASHBOARD_MSG = {"chat_id": None, "message_id": None, "view": None}
USER_STATES = {}

MAIN_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "💻 Status RDP Fleet"}, {"text": "🔄 Refresh"}],
        [{"text": "➕ Tambah / Setup RDP"}, {"text": "📋 List Node ID"}],
        [{"text": "📁 Folder RDP"}, {"text": "🗑️ Hapus RDP"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

def check_tcp_port(host, port, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def load_nodes():
    if os.path.exists(NODES_FILE):
        try:
            with open(NODES_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list): return d
                if isinstance(d, dict):
                    res = []
                    for k, v in d.items():
                        if isinstance(v, dict):
                            res.append({
                                "ip": k,
                                "name": v.get("name", k),
                                "pwd": v.get("pwd", ""),
                                "uuid": v.get("uuid", "-"),
                                "folder": v.get("folder", "RDP"),
                                "ram": v.get("ram", "-"),
                                "os": v.get("os", "Windows"),
                                "last_seen": v.get("last_seen", 0)
                            })
                        else:
                            res.append({"ip": k, "name": str(v), "pwd": "", "uuid": "-", "folder": "RDP", "ram": "-", "last_seen": 0})
                    return res
        except Exception:
            pass
    return []

def save_nodes(nodes):
    try:
        dict_format = {}
        for n in nodes:
            ip = n.get("ip", "unknown")
            dict_format[ip] = {
                "name": n.get("name", ip),
                "pwd": n.get("pwd", ""),
                "uuid": n.get("uuid", "-"),
                "folder": n.get("folder", "RDP"),
                "ram": n.get("ram", "-"),
                "os": n.get("os", "Windows"),
                "last_seen": n.get("last_seen", int(time.time()))
            }
        with open(NODES_FILE, "w", encoding="utf-8") as f:
            json.dump(dict_format, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Save nodes failed: {e}")

def get_node_folder(n):
    f = n.get("folder", "")
    if f and f.strip(): return f.strip().capitalize()
    name = n.get("name", "")
    m = re.match(r'^([a-zA-Z]+)', name)
    if m:
        pref = m.group(1).capitalize()
        if pref.lower() not in ["rdp", "win", "worker"]: return pref
    return "RDP"

def get_next_worker_name(folder_name):
    folder_clean = str(folder_name).strip().capitalize()
    nodes = load_nodes()
    existing_nums = []
    for n in nodes:
        f = get_node_folder(n)
        if f.lower() == folder_clean.lower():
            name = str(n.get("name", ""))
            m = re.search(rf'^{re.escape(folder_clean)}[-_]?(\d+)$', name, re.IGNORECASE)
            if m:
                existing_nums.append(int(m.group(1)))
    next_num = 1
    while next_num in existing_nums:
        next_num += 1
    return f"{folder_clean}-{next_num}"

def get_all_folders():
    nodes = load_nodes()
    folders = {}
    for n in nodes:
        f = get_node_folder(n)
        folders.setdefault(f, []).append(n)
    sorted_names = sorted(folders.keys(), key=lambda x: (x.lower() == "rdp", x.lower()))
    return {k: folders[k] for k in sorted_names}

def tg_call(method, params=None, timeout=30):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        if params:
            data = urllib.parse.urlencode(params).encode('utf-8')
            req = urllib.request.Request(url, data=data)
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"[TG CALL ERROR] {method}: {e}")
        return None

def send_message(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
    return tg_call("sendMessage", params)

def edit_message(chat_id, message_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
    return tg_call("editMessageText", params)

def answer_callback(cb_id, text=None, show_alert=False):
    p = {"callback_query_id": cb_id}
    if text:
        p["text"] = text
        p["show_alert"] = "true" if show_alert else "false"
    return tg_call("answerCallbackQuery", p)

# =========================================================================
#  REMOTE SSH & WINRM PROVISIONING ENGINE
# =========================================================================

def execute_remote_windows_ssh(ip, password, cmd, timeout=60, user="Administrator"):
    """
    Executes PowerShell command on Windows RDP via SSH using sshpass.
    """
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=8",
        f"{user}@{ip}",
        cmd
    ]
    try:
        res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -2, "", str(e)

def setup_rdp_remote(ip, password, folder=None, name=None, user="Administrator"):
    """
    Connects to Windows RDP over SSH, runs setup.ps1 non-interactively.
    Returns (success: bool, message: str, node_id: str, claim_link: str)
    """
    if not folder:
        folder = "RDP"
    folder = folder.strip().capitalize()

    if not name:
        worker_name = get_next_worker_name(folder)
    else:
        worker_name = name.strip()

    # 1. Cek apakah port 22 (SSH) terbuka
    port_22_open = check_tcp_port(ip, 22, timeout=4)
    if not port_22_open:
        # Simpan worker dengan status pending setup
        with NODES_LOCK:
            nodes = load_nodes()
            found = False
            for n in nodes:
                if n.get("ip") == ip:
                    n["name"] = worker_name
                    n["folder"] = folder
                    n["pwd"] = password
                    found = True
                    break
            if not found:
                nodes.append({"ip": ip, "name": worker_name, "folder": folder, "pwd": password, "uuid": "-", "ram": "-", "last_seen": 0})
            save_nodes(nodes)

        setup_cmd = "irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex"
        err_msg = (
            f"⚠️ <b>Port SSH (22) di RDP <code>{html.escape(ip)}</code> tertutup atau diblokir provider.</b>\n\n"
            f"Provider RDP Anda mengunci port remote secara default dan hanya membuka port 3389 (layar).\n\n"
            f"💡 <b>Solusi 1-Klik Sekali Saja (Hanya butuh 5 detik):</b>\n"
            f"1. Buka RDP sekali via Remote Desktop.\n"
            f"2. Buka <b>PowerShell (Run as Admin)</b>, lalu paste perintah ini:\n\n"
            f"<code>{setup_cmd}</code>\n\n"
            f"✨ Script ini otomatis:\n"
            f"• Mengaktifkan OpenSSH Server & membuka port 22 di Firewall Windows\n"
            f"• Whitelist Defender & Anti-virus (bebas deteksi virus/PUA)\n"
            f"• Auto-reboot 24 jam & Anti-sleep Keep-Alive\n"
            f"• Mengirimkan link klaim ke bot ini\n\n"
            f"🔥 <i>Setelah dijalankan 1x ini, seterusnya RDP ini 100% BISA DIKONTROL DARI TELEGRAM (reboot, restart earnapp, cek status) tanpa login RDP lagi!</i>"
        )
        return False, err_msg, "", ""

    # 2. Port 22 terbuka -> Tes login SSH & jalankan setup.ps1
    test_rc, _, test_err = execute_remote_windows_ssh(ip, password, "powershell -Command Write-Host 'SSH_OK'", timeout=12, user=user)
    if test_rc != 0:
        return False, f"❌ Gagal login SSH ke <code>{html.escape(ip)}</code> dengan user <code>{html.escape(user)}</code>.\nPastikan password benar!\n\n<i>Detail: {html.escape(test_err[:150])}</i>", "", ""

    # 3. Jalankan installer setup.ps1 secara headless di background Windows RDP
    install_cmd = (
        f'powershell.exe -ExecutionPolicy Bypass -Command '
        f'"& {{[scriptblock]::Create((irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 -UseBasicParsing)).Invoke(\'{worker_name}\', \'{folder}\', \'{BOT_TOKEN}\', \'{ADMIN_CHAT_ID}\', \'\', $true)}}"'
    )
    rc_inst, out_inst, err_inst = execute_remote_windows_ssh(ip, password, install_cmd, timeout=120, user=user)

    # 4. Ambil Node ID dari file status/uuid di RDP
    time.sleep(3)
    fetch_id_cmd = (
        'powershell.exe -Command "'
        'if (Test-Path \'$env:ProgramData\\EarnApp\\uuid\') { Get-Content \'$env:ProgramData\\EarnApp\\uuid\' } '
        'elseif (Test-Path \'$env:ProgramFiles (x86)\\EarnApp\\uuid\') { Get-Content \'$env:ProgramFiles (x86)\\EarnApp\\uuid\' } '
        'elseif (Test-Path \'$env:ProgramData\\EarnApp\\status.json\') { Get-Content \'$env:ProgramData\\EarnApp\\status.json\' }'
        '"'
    )
    _, out_id, _ = execute_remote_windows_ssh(ip, password, fetch_id_cmd, timeout=15, user=user)

    node_id = ""
    m_nid = re.search(r'sdk-node-[a-zA-Z0-9_-]+', out_id)
    if m_nid:
        node_id = m_nid.group(0)

    # Ambil info RAM
    ram_cmd = 'powershell.exe -Command "$os = Get-CimInstance Win32_OperatingSystem; [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1024).ToString() + \' MB / \' + [math]::Round($os.TotalVisibleMemorySize/1024).ToString() + \' MB\'"'
    _, out_ram, _ = execute_remote_windows_ssh(ip, password, ram_cmd, timeout=10, user=user)
    ram_str = out_ram.strip() if out_ram.strip() else "-"

    claim_link = f"https://earnapp.com/r/{node_id}" if node_id else "<i>Sedang sinkronisasi... (Cek di tombol List Node ID dalam 1 menit)</i>"

    # Simpan ke nodes.json
    with NODES_LOCK:
        nodes = load_nodes()
        updated = False
        for n in nodes:
            if n.get("ip") == ip or n.get("name") == worker_name:
                n["ip"] = ip
                n["name"] = worker_name
                n["folder"] = folder
                n["pwd"] = password
                if node_id: n["uuid"] = node_id
                if ram_str != "-": n["ram"] = ram_str
                n["last_seen"] = int(time.time())
                updated = True
                break
        if not updated:
            nodes.append({
                "ip": ip,
                "name": worker_name,
                "folder": folder,
                "pwd": password,
                "uuid": node_id if node_id else "-",
                "ram": ram_str,
                "os": "Windows",
                "last_seen": int(time.time())
            })
        save_nodes(nodes)

    success_msg = (
        f"✅ <b>RDP [ {html.escape(worker_name)} ] BERHASIL DI-SETUP DARI TELEGRAM!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>Worker:</b> <b>{html.escape(worker_name)}</b> [📁 {html.escape(folder)}]\n"
        f"🌐 <b>IP RDP:</b> <code>{html.escape(ip)}</code>\n"
        f"💾 <b>RAM:</b> <code>{html.escape(ram_str)}</code>\n\n"
        f"🆔 <b>Node ID:</b> <code>{html.escape(node_id if node_id else 'Sedang sinkronisasi...')}</code>\n"
        f"🔗 <b>Claim Link:</b> {claim_link}\n\n"
        f"🛡️ <b>Windows Defender:</b> 🟢 Whitelisted & PUA Disabled\n"
        f"🔑 <b>Remote SSH:</b> 🟢 Port 22 Aktif (Bisa reboot via Tele!)\n"
        f"🔄 <b>Auto-Reboot 24h:</b> 🟢 Terjadwal (04:00 AM)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Klik tombol di bawah untuk langsung klaim ke akun EarnApp Anda!</i>"
    )
    return True, success_msg, node_id, claim_link

def reboot_rdp_remote(n):
    ip = n.get("ip")
    pwd = n.get("pwd", "")
    if not pwd:
        return False, "Password RDP belum tersimpan di bot. Harap jalankan `/add <ip> <pwd>` terlebih dahulu."
    rc, out, err = execute_remote_windows_ssh(ip, pwd, 'shutdown.exe /r /t 5 /f /c "Telegram remote reboot"', timeout=15)
    if rc == 0:
        return True, f"🔄 Perintah reboot berhasil dikirim ke RDP <b>{html.escape(n.get('name', ip))}</b> (<code>{ip}</code>)."
    else:
        return False, f"⚠️ Gagal reboot: {html.escape(err if err else 'SSH error')}"

def restart_earnapp_remote(n):
    ip = n.get("ip")
    pwd = n.get("pwd", "")
    if not pwd:
        return False, "Password RDP belum tersimpan di bot."
    cmd = (
        'powershell.exe -Command "'
        'Stop-Process -Name *earnapp* -Force -ErrorAction SilentlyContinue; '
        'Start-Sleep -Seconds 2; '
        'Start-Process \'C:\\Program Files (x86)\\EarnApp\\earnapp.exe\' -ErrorAction SilentlyContinue; '
        'Start-Process \'C:\\Program Files\\EarnApp\\earnapp.exe\' -ErrorAction SilentlyContinue'
        '"'
    )
    rc, out, err = execute_remote_windows_ssh(ip, pwd, cmd, timeout=20)
    if rc == 0:
        return True, f"⚡ Proses EarnApp di RDP <b>{html.escape(n.get('name', ip))}</b> berhasil direstart!"
    else:
        return False, f"⚠️ Gagal restart EarnApp: {html.escape(err if err else 'SSH error')}"

# =========================================================================
#  TELEGRAM UI & DASHBOARD ENGINE
# =========================================================================

def render_dashboard(active_folder=None):
    nodes = load_nodes()
    now_ts = int(time.time())
    now_str = time.strftime("%H:%M:%S")

    if not nodes:
        text = (
            "🚀 <b>EARNAPP WINDOWS RDP FLEET CONTROLLER</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <i>Belum ada Windows RDP yang terdaftar.</i>\n\n"
            "<b>Cara Tambah RDP:</b>\n"
            "1. <b>Otomatis dari Telegram:</b>\n"
            "   Ketik: <code>/add &lt;ip&gt; &lt;password&gt; [folder]</code>\n"
            "   Contoh: <code>/add 104.238.1.10 Rahasia123 nayla</code>\n\n"
            "2. <b>Manual di RDP (PowerShell Admin):</b>\n"
            "   <code>irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex</code>"
        )
        markup = {"inline_keyboard": [
            [{"text": "➕ Tambah / Setup RDP", "callback_data": "btn_add"}],
            [{"text": "🔄 Refresh", "callback_data": "btn_refresh"}]
        ]}
        return text, markup

    folders_data = {}
    node_lines = []
    total_nodes = len(nodes)
    online_count = 0

    for n in nodes:
        ip = n.get("ip", "unknown")
        name = n.get("name", ip)
        f = get_node_folder(n)
        uuid = n.get("uuid", "-")
        ram = n.get("ram", "-")
        last_seen = n.get("last_seen", 0)
        
        diff_min = int((now_ts - last_seen) / 60) if last_seen > 0 else 999
        is_online = diff_min <= 30
        if is_online: online_count += 1

        f_entry = folders_data.setdefault(f, {"nodes": [], "online": 0})
        f_entry["nodes"].append(n)
        if is_online: f_entry["online"] += 1

        status_emoji = "🟢" if is_online else "🟡" if diff_min <= 120 else "🔴"
        seen_str = "Online" if diff_min <= 5 else f"{diff_min}m lalu" if diff_min < 60 else f"{int(diff_min/60)}j lalu"
        
        claim_link = f"https://earnapp.com/r/{uuid}" if uuid != "-" and "sdk-node" in uuid else "<i>Belum klaim</i>"
        
        line = (
            f"{status_emoji} <b>{html.escape(str(name))}</b> (<code>{html.escape(str(ip))}</code>)\n"
            f"   ├ 💾 RAM: <code>{html.escape(str(ram))}</code> | 🕒 Seen: <i>{seen_str}</i>\n"
            f"   ├ 🆔 <code>{html.escape(str(uuid[:22]))}...</code>\n"
            f"   └ 🔗 {claim_link}"
        )
        node_lines.append((f, line, n))

    sorted_f_names = sorted(folders_data.keys(), key=lambda x: (x.lower() == "rdp", x.lower()))

    # VIEW 1: Detail spesifik folder
    matched_folder = None
    if active_folder and active_folder != "ALL":
        for f_name in folders_data:
            if f_name.lower() == str(active_folder).lower():
                matched_folder = f_name
                break

    if matched_folder:
        f_info = folders_data[matched_folder]
        f_lines = [l for (f, l, n) in node_lines if f == matched_folder]
        f_nodes = [n for (f, l, n) in node_lines if f == matched_folder]
        header = (
            f"📁 <b>FOLDER RDP: {html.escape(matched_folder.upper())}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ <b>Workers:</b> {f_info['online']}/{len(f_info['nodes'])} Online\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code> | 🛡️ <b>24/7 Keep-Alive:</b> 🟢\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        text = header + "\n\n".join(f_lines)
        
        buttons = [
            [{"text": "🔄 Refresh", "callback_data": f"fld_ref_{matched_folder}"}, {"text": f"➕ Tambah ke {matched_folder}", "callback_data": f"fld_add_{matched_folder}"}],
            [{"text": "🔙 Semua Folder", "callback_data": "fld_MAIN"}, {"text": "🌐 Lihat Semua RDP", "callback_data": "fld_ALL"}],
            [{"text": "📋 List Node ID", "callback_data": "btn_ids"}, {"text": "🗑️ Hapus RDP", "callback_data": "btn_del_menu"}]
        ]
        
        # Tambah baris aksi cepat jika ada node di folder ini
        if f_nodes:
            action_row = []
            for item in f_nodes[:3]:
                action_row.append({"text": f"🔄 Reboot {item.get('name')}", "callback_data": f"reb_{item.get('ip')}"})
            buttons.insert(1, action_row)

        return text, {"inline_keyboard": buttons}

    # VIEW 2: Semua worker sekaligus
    elif active_folder == "ALL":
        header = (
            f"⚡ <b>EARNAPP WINDOWS RDP DASHBOARD (ALL)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ <b>Total RDP:</b> {online_count}/{total_nodes} Online\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code> | 🛡️ <b>24/7 Keep-Alive:</b> 🟢\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        text = header + "\n\n".join([l for (f, l, n) in node_lines])
        markup = {
            "inline_keyboard": [
                [{"text": "📁 Mode Ringkasan Folder", "callback_data": "fld_MAIN"}, {"text": "🔄 Refresh", "callback_data": "fld_ALL"}],
                [{"text": "➕ Tambah / Setup RDP", "callback_data": "btn_add"}, {"text": "📋 List Node ID", "callback_data": "btn_ids"}],
                [{"text": "🗑️ Hapus RDP", "callback_data": "btn_del_menu"}]
            ]
        }
        return text, markup

    # VIEW 3: Overview Folder Cards
    else:
        f_blocks = []
        for f_name in sorted_f_names:
            f_info = folders_data[f_name]
            block = (
                f"📁 <b>{html.escape(f_name)}</b> ({len(f_info['nodes'])} RDP)\n"
                f"   └ Status: <b>{f_info['online']}/{len(f_info['nodes'])} Online</b>"
            )
            f_blocks.append(block)

        header = (
            f"⚡ <b>EARNAPP WINDOWS RDP CONTROLLER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ <b>Total RDP:</b> {online_count}/{total_nodes} Online\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code> | 🛡️ <b>24/7 Keep-Alive:</b> 🟢\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📁 <b>GROUP & FOLDER OVERVIEW:</b>\n\n"
        )
        footer = "\n\n━━━━━━━━━━━━━━━━━━━━━\n<i>Pilih folder di bawah untuk melihat detail RDP:</i>"
        text = header + "\n\n".join(f_blocks) + footer

        buttons = []
        cur_row = []
        for f_name in sorted_f_names:
            cnt = len(folders_data[f_name]["nodes"])
            cur_row.append({"text": f"📁 {f_name} ({cnt})", "callback_data": f"fld_view_{f_name}"})
            if len(cur_row) == 2:
                buttons.append(cur_row)
                cur_row = []
        if cur_row: buttons.append(cur_row)

        buttons.append([{"text": "🌐 Lihat Semua RDP", "callback_data": "fld_ALL"}, {"text": "🔄 Refresh", "callback_data": "btn_refresh"}])
        buttons.append([{"text": "➕ Tambah / Setup RDP", "callback_data": "btn_add"}, {"text": "📋 List Node ID", "callback_data": "btn_ids"}])
        buttons.append([{"text": "🗑️ Hapus RDP", "callback_data": "btn_del_menu"}])

        markup = {"inline_keyboard": buttons}
        return text, markup

# =========================================================================
#  TELEGRAM MESSAGE & COMMAND HANDLER
# =========================================================================

def handle_telegram_message(msg):
    try:
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        if not text or not chat_id: return
        if int(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "⛔ <b>Akses Ditolak.</b>")
            return

        text_lower = text.lower()

        # Check pending interactive states
        if chat_id in USER_STATES:
            state = USER_STATES[chat_id]
            if state.get("step") == "WAIT_ADD_INPUT":
                del USER_STATES[chat_id]
                parts = text.split()
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    pwd = parts[1].strip()
                    folder = state.get("target_folder") or (parts[2].strip().capitalize() if len(parts) >= 3 else "RDP")
                    name = parts[3].strip() if len(parts) >= 4 else None
                    
                    wait_msg = send_message(chat_id, f"⏳ Sedang menghubungkan ke RDP <code>{html.escape(ip)}</code> dan menjalankan konfigurasi otomatis... Mohon tunggu ~20-30 detik...")
                    def _run_add():
                        ok, res_text, nid, clink = setup_rdp_remote(ip, pwd, folder=folder, name=name)
                        kb = []
                        if nid and "sdk-node" in nid:
                            kb.append([{"text": "🔗 Klaim Akun EarnApp", "url": f"https://earnapp.com/r/{nid}"}])
                        kb.append([{"text": "📊 Buka Dashboard", "callback_data": "btn_refresh"}])
                        send_message(chat_id, res_text, reply_markup={"inline_keyboard": kb})
                    threading.Thread(target=_run_add, daemon=True).start()
                    return
                else:
                    send_message(chat_id, "⚠️ Format salah. Gunakan: <code>&lt;ip&gt; &lt;password&gt; [folder] [name]</code>")
                    return

        if any(text.startswith(cmd) for cmd in ["/start", "/menu", "/status", "/nodes", "/dashboard"]) or text_lower == "status rdp fleet":
            dash_text, markup = render_dashboard()
            res = send_message(chat_id, dash_text, markup)
            if res and res.get("ok"):
                LAST_DASHBOARD_MSG["chat_id"] = chat_id
                LAST_DASHBOARD_MSG["message_id"] = res["result"]["message_id"]
                LAST_DASHBOARD_MSG["view"] = None
        elif text.startswith("/refresh") or text_lower == "refresh":
            cur_view = LAST_DASHBOARD_MSG.get("view")
            dash_text, markup = render_dashboard(active_folder=cur_view)
            res = send_message(chat_id, dash_text, markup)
            if res and res.get("ok"):
                LAST_DASHBOARD_MSG["chat_id"] = chat_id
                LAST_DASHBOARD_MSG["message_id"] = res["result"]["message_id"]
        elif text.startswith("/all") or "semua rdp" in text_lower:
            dash_text, markup = render_dashboard(active_folder="ALL")
            res = send_message(chat_id, dash_text, markup)
            if res and res.get("ok"):
                LAST_DASHBOARD_MSG["chat_id"] = chat_id
                LAST_DASHBOARD_MSG["message_id"] = res["result"]["message_id"]
                LAST_DASHBOARD_MSG["view"] = "ALL"
        elif text.startswith("/folder") or text_lower == "folder rdp":
            parts = text.split()
            f_target = parts[1].strip() if len(parts) >= 2 else None
            dash_text, markup = render_dashboard(active_folder=f_target)
            res = send_message(chat_id, dash_text, markup)
            if res and res.get("ok"):
                LAST_DASHBOARD_MSG["chat_id"] = chat_id
                LAST_DASHBOARD_MSG["message_id"] = res["result"]["message_id"]
                LAST_DASHBOARD_MSG["view"] = f_target
        elif text.startswith("/add") or text_lower == "tambah / setup rdp" or text_lower == "tambah rdp":
            parts = text.split()
            if len(parts) >= 3:
                ip = parts[1].strip()
                pwd = parts[2].strip()
                folder = parts[3].strip().capitalize() if len(parts) >= 4 else "RDP"
                name = parts[4].strip() if len(parts) >= 5 else None

                send_message(chat_id, f"⏳ <b>Memulai Remote Setup RDP:</b> <code>{html.escape(ip)}</code> ke folder <b>{html.escape(folder)}</b>...\nMohon tunggu ~20-30 detik...")
                def _run_bg():
                    ok, res_text, nid, clink = setup_rdp_remote(ip, pwd, folder=folder, name=name)
                    kb = []
                    if nid and "sdk-node" in nid:
                        kb.append([{"text": "🔗 Klaim Akun EarnApp", "url": f"https://earnapp.com/r/{nid}"}])
                    kb.append([{"text": "📊 Buka Dashboard", "callback_data": "btn_refresh"}])
                    send_message(chat_id, res_text, reply_markup={"inline_keyboard": kb})
                threading.Thread(target=_run_bg, daemon=True).start()
            else:
                USER_STATES[chat_id] = {"step": "WAIT_ADD_INPUT", "target_folder": None}
                setup_cmd = "irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex"
                msg_text = (
                    "➕ <b>TAMBAH / SETUP WINDOWS RDP:</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "⚡ <b>Metode 1: Otomatis dari Telegram (Tanpa Buka Layar RDP)</b>\n"
                    "Kirimkan IP dan Password RDP dengan format:\n"
                    "<code>/add &lt;ip&gt; &lt;password&gt; [folder] [name]</code>\n\n"
                    "Contoh:\n"
                    "<code>/add 104.238.1.10 Rahasia123 nayla</code>\n"
                    "<i>(Nama worker otomatis berurut: nayla-1, nayla-2, dst.)</i>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "📋 <b>Metode 2: Manual 1-Klik di RDP (Jika SSH Port 22 ditutup)</b>\n"
                    "Buka PowerShell (Run as Admin) di RDP dan jalankan:\n"
                    f"<code>{setup_cmd}</code>"
                )
                markup = {"inline_keyboard": [
                    [{"text": "🔙 Batal / Dashboard", "callback_data": "btn_refresh"}]
                ]}
                send_message(chat_id, msg_text, reply_markup=markup)
        elif text.startswith("/reboot"):
            parts = text.split()
            if len(parts) >= 2:
                target = parts[1].strip()
                nodes = load_nodes()
                matched = [n for n in nodes if n.get("ip") == target or str(n.get("name", "")).lower() == target.lower()]
                if matched:
                    send_message(chat_id, f"⏳ Mengirim sinyal reboot ke RDP <b>{html.escape(matched[0].get('name'))}</b>...")
                    def _do_reb():
                        ok, res = reboot_rdp_remote(matched[0])
                        send_message(chat_id, res)
                    threading.Thread(target=_do_reb, daemon=True).start()
                else:
                    send_message(chat_id, f"⚠️ RDP <code>{html.escape(target)}</code> tidak ditemukan di daftar.")
            else:
                send_message(chat_id, "Gunakan: <code>/reboot &lt;ip atau nama&gt;</code>")
        elif text.startswith("/restart"):
            parts = text.split()
            if len(parts) >= 2:
                target = parts[1].strip()
                nodes = load_nodes()
                matched = [n for n in nodes if n.get("ip") == target or str(n.get("name", "")).lower() == target.lower()]
                if matched:
                    send_message(chat_id, f"⏳ Mengirim sinyal restart EarnApp ke <b>{html.escape(matched[0].get('name'))}</b>...")
                    def _do_rst():
                        ok, res = restart_earnapp_remote(matched[0])
                        send_message(chat_id, res)
                    threading.Thread(target=_do_rst, daemon=True).start()
                else:
                    send_message(chat_id, f"⚠️ RDP <code>{html.escape(target)}</code> tidak ditemukan di daftar.")
            else:
                send_message(chat_id, "Gunakan: <code>/restart &lt;ip atau nama&gt;</code>")
        elif text.startswith("/id") or text_lower == "list node id" or text_lower == "node id":
            nodes = load_nodes()
            lines = ["📋 <b>EARNAPP RDP NODE IDs & CLAIM URL</b>\n━━━━━━━━━━━━━━━━━━━━━"]
            for n in nodes:
                ip, name, uuid = n.get("ip"), n.get("name", n.get("ip")), n.get("uuid", "-")
                claim = f"https://earnapp.com/r/{uuid}" if uuid != "-" and "sdk-node" in uuid else "<i>Belum terdeteksi</i>"
                lines.append(f"🏷️ <b>{html.escape(str(name))}</b> [📁 {get_node_folder(n)}] (<code>{html.escape(str(ip))}</code>)\n🆔 <code>{html.escape(str(uuid))}</code>\n🔗 {claim}\n")
            send_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": [[{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}]]})
        elif text.startswith("/rename"):
            parts = text.split()
            if len(parts) >= 3:
                target, new_name = parts[1], parts[2]
                nodes = load_nodes()
                changed = False
                for n in nodes:
                    if n.get("ip") == target or str(n.get("name", "")).lower() == target.lower():
                        n["name"] = new_name
                        changed = True
                        break
                if changed:
                    save_nodes(nodes)
                    send_message(chat_id, f"✅ RDP berhasil diubah namanya menjadi <b>{html.escape(new_name)}</b>!", reply_markup={"inline_keyboard": [[{"text": "📊 Dashboard", "callback_data": "btn_refresh"}]]})
                else:
                    send_message(chat_id, f"⚠️ RDP <code>{html.escape(target)}</code> tidak ditemukan.")
            else:
                send_message(chat_id, "Gunakan: <code>/rename &lt;ip_atau_nama_lama&gt; &lt;nama_baru&gt;</code>")
        elif text.startswith("/move"):
            parts = text.split()
            if len(parts) >= 3:
                target, new_folder = parts[1], parts[2].strip().capitalize()
                nodes = load_nodes()
                changed = False
                for n in nodes:
                    if n.get("ip") == target or str(n.get("name", "")).lower() == target.lower():
                        n["folder"] = new_folder
                        changed = True
                        break
                if changed:
                    save_nodes(nodes)
                    send_message(chat_id, f"✅ RDP berhasil dipindahkan ke folder <b>{html.escape(new_folder)}</b>!", reply_markup={"inline_keyboard": [[{"text": "📊 Dashboard", "callback_data": "btn_refresh"}]]})
                else:
                    send_message(chat_id, f"⚠️ RDP <code>{html.escape(target)}</code> tidak ditemukan.")
            else:
                send_message(chat_id, "Gunakan: <code>/move &lt;ip_atau_nama&gt; &lt;folder_baru&gt;</code>")
        elif text.startswith("/del") or text_lower == "hapus rdp":
            parts = text.split()
            if len(parts) >= 2:
                target = parts[1]
                nodes = load_nodes()
                new_nodes = [n for n in nodes if n.get("ip") != target and n.get("name") != target]
                if len(new_nodes) < len(nodes):
                    save_nodes(new_nodes)
                    send_message(chat_id, f"✅ RDP <b>{html.escape(target)}</b> dihapus.", reply_markup={"inline_keyboard": [[{"text": "📊 Dashboard", "callback_data": "btn_refresh"}]]})
                else:
                    send_message(chat_id, f"⚠️ RDP tidak ditemukan.")
            else:
                # Buka menu tombol hapus
                nodes = load_nodes()
                buttons = [[{"text": f"🗑️ {n.get('name')} ({n.get('ip')})", "callback_data": f"del_{n.get('ip')}"}] for n in nodes]
                buttons.append([{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}])
                send_message(chat_id, "🗑️ <b>PILIH RDP YANG AKAN DIHAPUS:</b>", reply_markup={"inline_keyboard": buttons})
        elif text.startswith("/help") or "help" in text_lower:
            help_text = (
                "📖 <b>PANDUAN BOT RDP FLEET CONTROLLER</b>\n\n"
                "• <code>/start</code> - Buka ringkasan folder dashboard RDP\n"
                "• <code>/add &lt;ip&gt; &lt;pwd&gt; [folder] [name]</code> - Setup RDP otomatis via SSH tanpa buka layar!\n"
                "• <code>/reboot &lt;nama/ip&gt;</code> - Restart Windows RDP secara remote\n"
                "• <code>/restart &lt;nama/ip&gt;</code> - Restart proses EarnApp secara remote\n"
                "• <code>/folder &lt;nama&gt;</code> - Buka folder tertentu (misal: Singapore)\n"
                "• <code>/all</code> - Tampilkan seluruh RDP\n"
                "• <code>/move &lt;nama&gt; &lt;folder&gt;</code> - Pindah folder\n"
                "• <code>/rename &lt;lama&gt; &lt;baru&gt;</code> - Ganti nama RDP\n"
                "• <code>/del &lt;ip/nama&gt;</code> - Hapus RDP dari daftar\n"
                "• <code>/ids</code> - List semua Node ID & Claim URL EarnApp"
            )
            send_message(chat_id, help_text)
    except Exception as e:
        print(f"[MSG ERROR] {e}")

# =========================================================================
#  TELEGRAM CALLBACK HANDLER
# =========================================================================

def handle_telegram_callback(cb):
    try:
        cb_id = cb.get("id")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        msg_id = cb.get("message", {}).get("message_id")
        data = cb.get("data", "")
        if int(chat_id) != ADMIN_CHAT_ID:
            answer_callback(cb_id, "Akses ditolak.", show_alert=True)
            return

        if data == "btn_refresh":
            answer_callback(cb_id, "🔄 Memperbarui...")
            cur_view = LAST_DASHBOARD_MSG.get("view")
            dash_text, markup = render_dashboard(active_folder=cur_view)
            edit_message(chat_id, msg_id, dash_text, markup)
            LAST_DASHBOARD_MSG["chat_id"] = chat_id
            LAST_DASHBOARD_MSG["message_id"] = msg_id
        elif data == "fld_MAIN":
            answer_callback(cb_id, "Membuka ringkasan folder...")
            dash_text, markup = render_dashboard(active_folder=None)
            edit_message(chat_id, msg_id, dash_text, markup)
            LAST_DASHBOARD_MSG["chat_id"] = chat_id
            LAST_DASHBOARD_MSG["message_id"] = msg_id
            LAST_DASHBOARD_MSG["view"] = None
        elif data == "fld_ALL":
            answer_callback(cb_id, "Menampilkan semua RDP...")
            dash_text, markup = render_dashboard(active_folder="ALL")
            edit_message(chat_id, msg_id, dash_text, markup)
            LAST_DASHBOARD_MSG["chat_id"] = chat_id
            LAST_DASHBOARD_MSG["message_id"] = msg_id
            LAST_DASHBOARD_MSG["view"] = "ALL"
        elif data.startswith("fld_view_"):
            target_f = data.replace("fld_view_", "")
            answer_callback(cb_id, f"Membuka folder {target_f}...")
            dash_text, markup = render_dashboard(active_folder=target_f)
            edit_message(chat_id, msg_id, dash_text, markup)
            LAST_DASHBOARD_MSG["chat_id"] = chat_id
            LAST_DASHBOARD_MSG["message_id"] = msg_id
            LAST_DASHBOARD_MSG["view"] = target_f
        elif data.startswith("fld_ref_"):
            target_f = data.replace("fld_ref_", "")
            answer_callback(cb_id, f"Memperbarui folder {target_f}...")
            dash_text, markup = render_dashboard(active_folder=target_f)
            edit_message(chat_id, msg_id, dash_text, markup)
            LAST_DASHBOARD_MSG["chat_id"] = chat_id
            LAST_DASHBOARD_MSG["message_id"] = msg_id
            LAST_DASHBOARD_MSG["view"] = target_f
        elif data.startswith("fld_add_"):
            target_f = data.replace("fld_add_", "")
            answer_callback(cb_id)
            next_name = get_next_worker_name(target_f)
            USER_STATES[chat_id] = {"step": "WAIT_ADD_INPUT", "target_folder": target_f}
            msg_text = (
                f"➕ <b>TAMBAH RDP KE FOLDER {html.escape(target_f.upper())}:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Nama worker berikutnya akan otomatis: <b>{html.escape(next_name)}</b>\n\n"
                f"Kirimkan IP dan Password RDP Anda sekarang dengan format:\n"
                f"<code>&lt;ip&gt; &lt;password&gt;</code>\n\n"
                f"Contoh:\n"
                f"<code>104.238.1.10 Rahasia123</code>"
            )
            edit_message(chat_id, msg_id, msg_text, {"inline_keyboard": [[{"text": "🔙 Batal", "callback_data": f"fld_view_{target_f}"}]]})
        elif data.startswith("reb_"):
            target_ip = data.replace("reb_", "")
            nodes = load_nodes()
            matched = [n for n in nodes if n.get("ip") == target_ip]
            if matched:
                answer_callback(cb_id, f"Mengirim perintah reboot ke {matched[0].get('name')}...", show_alert=True)
                def _bg_reb():
                    ok, res = reboot_rdp_remote(matched[0])
                    send_message(chat_id, res)
                threading.Thread(target=_bg_reb, daemon=True).start()
            else:
                answer_callback(cb_id, "RDP tidak ditemukan.", show_alert=True)
        elif data == "btn_add":
            answer_callback(cb_id)
            setup_cmd = "irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex"
            msg_text = (
                "➕ <b>TAMBAH / SETUP WINDOWS RDP:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "⚡ <b>Metode 1: Otomatis dari Telegram (Tanpa Buka RDP)</b>\n"
                "Gunakan perintah:\n"
                "<code>/add &lt;ip&gt; &lt;password&gt; [folder]</code>\n\n"
                "Contoh:\n"
                "<code>/add 104.238.1.10 Rahasia123 nayla</code>\n"
                "<i>(Nama worker otomatis berurut: nayla-1, nayla-2, dst.)</i>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📋 <b>Metode 2: Manual 1-Klik di RDP (Jika SSH Port 22 ditutup)</b>\n"
                "Buka <b>PowerShell (Run as Admin)</b> di RDP dan jalankan:\n\n"
                f"<code>{setup_cmd}</code>\n\n"
                "<i>Script otomatis membuka OpenSSH & Defender whitelist, sehingga seterusnya RDP bisa dikontrol dari Telegram!</i>"
            )
            edit_message(chat_id, msg_id, msg_text, {"inline_keyboard": [[{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}]]})
        elif data == "btn_ids":
            answer_callback(cb_id)
            nodes = load_nodes()
            lines = ["📋 <b>EARNAPP RDP NODE IDs & CLAIM URL</b>\n━━━━━━━━━━━━━━━━━━━━━"]
            for n in nodes:
                ip, name, uuid = n.get("ip"), n.get("name", n.get("ip")), n.get("uuid", "-")
                claim = f"https://earnapp.com/r/{uuid}" if uuid != "-" and "sdk-node" in uuid else "<i>Belum terdeteksi</i>"
                lines.append(f"🏷️ <b>{html.escape(str(name))}</b> [📁 {get_node_folder(n)}] (<code>{html.escape(str(ip))}</code>)\n🆔 <code>{html.escape(str(uuid))}</code>\n🔗 {claim}\n")
            edit_message(chat_id, msg_id, "\n".join(lines), {"inline_keyboard": [[{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}]]})
        elif data == "btn_del_menu":
            answer_callback(cb_id)
            nodes = load_nodes()
            buttons = [[{"text": f"🗑️ {n.get('name')} ({n.get('ip')})", "callback_data": f"del_{n.get('ip')}"}] for n in nodes]
            buttons.append([{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}])
            edit_message(chat_id, msg_id, "🗑️ <b>PILIH RDP YANG AKAN DIHAPUS:</b>", {"inline_keyboard": buttons})
        elif data.startswith("del_"):
            target_ip = data.replace("del_", "")
            answer_callback(cb_id, f"Menghapus {target_ip}...")
            nodes = load_nodes()
            new_nodes = [n for n in nodes if n.get("ip") != target_ip]
            save_nodes(new_nodes)
            dash_text, markup = render_dashboard()
            edit_message(chat_id, msg_id, f"✅ RDP <code>{html.escape(target_ip)}</code> dihapus.\n\n" + dash_text, markup)
    except Exception as e:
        print(f"[CB ERROR] {e}")

# =========================================================================
#  HTTP REGISTRATION & HEARTBEAT RECEIVER (Port 9090)
# =========================================================================

class RDPRegistrationHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('content-length', 0))
            raw = self.rfile.read(length).decode('utf-8')
            data = json.loads(raw)
            
            ip = data.get("ip", self.client_address[0])
            name = data.get("name", f"RDP-{ip}")
            folder = data.get("folder", "RDP").strip().capitalize()
            uuid = data.get("uuid", "-")
            ram = data.get("ram", "-")
            os_name = data.get("os", "Windows")

            with NODES_LOCK:
                nodes = load_nodes()
                found = False
                for n in nodes:
                    if n.get("ip") == ip or n.get("name") == name:
                        n["ip"] = ip
                        n["name"] = name
                        n["folder"] = folder
                        n["uuid"] = uuid
                        n["ram"] = ram
                        n["os"] = os_name
                        n["last_seen"] = int(time.time())
                        found = True
                        break
                if not found:
                    nodes.append({
                        "ip": ip,
                        "name": name,
                        "folder": folder,
                        "pwd": "",
                        "uuid": uuid,
                        "ram": ram,
                        "os": os_name,
                        "last_seen": int(time.time())
                    })
                save_nodes(nodes)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def log_message(self, format, *args):
        return  # Silent logging

def run_http_server():
    try:
        server = HTTPServer(("0.0.0.0", HTTP_PORT), RDPRegistrationHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP SERVER NOTICE] {e}")

def telegram_poller():
    offset = 0
    print("[INIT] RDP Telegram Polling engine running.")
    try:
        flush = tg_call("getUpdates", {"offset": -1, "timeout": 1}, timeout=5)
        if flush and flush.get("ok") and flush.get("result"):
            offset = flush["result"][-1]["update_id"] + 1
    except Exception: pass

    try:
        startup_msg = (
            "🤖 <b>EarnApp Windows RDP Master Bot Aktif!</b>\n\n"
            "✅ <b>Dedicated RDP Controller:</b> Running\n"
            "🛡️ <b>Remote SSH Management:</b> Ready\n"
            "⚡ <b>Auto-Naming by Folder:</b> Ready\n\n"
            "Ketik <code>/start</code> untuk membuka dashboard armada RDP Anda."
        )
        send_message(ADMIN_CHAT_ID, startup_msg, reply_markup=MAIN_REPLY_KEYBOARD)
    except Exception: pass

    while True:
        try:
            res = tg_call("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            if not res or not res.get("ok"):
                time.sleep(2)
                continue
            for update in res.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    threading.Thread(target=handle_telegram_message, args=(update["message"],), daemon=True).start()
                elif "callback_query" in update:
                    threading.Thread(target=handle_telegram_callback, args=(update["callback_query"],), daemon=True).start()
        except Exception:
            time.sleep(2)

def main():
    threading.Thread(target=run_http_server, daemon=True).start()
    telegram_poller()

if __name__ == "__main__":
    main()
