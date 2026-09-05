#!/usr/bin/env python3
"""
EarnApp Windows RDP Fleet Master Controller Bot
- Dedicated Telegram Bot for Windows RDP fleet management (@RdpfleetBot)
- Architecture: Outbound Stealth Agent (0 Open Ports on Windows RDPs!)
- Master Command Queue: Remote Reboot & Restart EarnApp delivered via 15s Heartbeat
- Automatic worker naming based on folder (e.g. nayla-1, nayla-2, nayla-3)
- Multi-folder & grouping system
- Node ID & Claim URL tracker with 1-click inline buttons
- Built-in HTTP listener (port 9090) for agent heartbeats & task execution
"""

import os
import sys
import time
import json
import re
import html
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
    "http_port": 9090,
    "master_ip": "47.237.82.102"
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
    return cfg.get("bot_token"), int(cfg.get("allowed_chat_id", 1943547868)), int(cfg.get("http_port", 9090)), cfg.get("master_ip", "AUTO")

BOT_TOKEN, ADMIN_CHAT_ID, HTTP_PORT, CFG_MASTER_IP = load_config()

NODES_LOCK = threading.Lock()
LAST_DASHBOARD_MSG = {"chat_id": None, "message_id": None, "view": None}
USER_STATES = {}
PENDING_COMMANDS = {}  # key: ip or name, value: {"command": "reboot"|"restart_earnapp", "cmd_id": "...", "timestamp": ...}

MASTER_PUBLIC_IP = None

def get_master_public_ip():
    global MASTER_PUBLIC_IP
    if MASTER_PUBLIC_IP:
        return MASTER_PUBLIC_IP
    if CFG_MASTER_IP and CFG_MASTER_IP != "AUTO":
        MASTER_PUBLIC_IP = CFG_MASTER_IP
        return MASTER_PUBLIC_IP
    for url in ["https://api.ipify.org", "https://icanhazip.com", "https://checkip.amazonaws.com"]:
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                ip = r.read().decode('utf-8').strip()
                if ip:
                    MASTER_PUBLIC_IP = ip
                    return ip
        except Exception:
            pass
    return "IP_VPS_MASTER"

MAIN_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "💻 Status RDP Fleet"}, {"text": "🔄 Refresh"}],
        [{"text": "➕ Tambah / Setup RDP"}, {"text": "📋 List Node ID"}],
        [{"text": "📁 Folder RDP"}, {"text": "🗑️ Hapus RDP"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

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
                                "uuid": v.get("uuid", "-"),
                                "folder": v.get("folder", "RDP"),
                                "ram": v.get("ram", "-"),
                                "status": v.get("status", "running"),
                                "uptime": v.get("uptime", "-"),
                                "os": v.get("os", "Windows"),
                                "last_seen": v.get("last_seen", 0)
                            })
                        else:
                            res.append({"ip": k, "name": str(v), "uuid": "-", "folder": "RDP", "ram": "-", "last_seen": 0})
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
                "uuid": n.get("uuid", "-"),
                "folder": n.get("folder", "RDP"),
                "ram": n.get("ram", "-"),
                "status": n.get("status", "running"),
                "uptime": n.get("uptime", "-"),
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

def queue_command(target_id, command):
    """
    Queues a command ('reboot' or 'restart_earnapp') for a specific RDP.
    Delivered automatically on the next 15-second heartbeat.
    """
    cmd_id = f"{command}_{int(time.time())}"
    with NODES_LOCK:
        nodes = load_nodes()
        found = False
        target_name = target_id
        for n in nodes:
            if n.get("ip") == target_id or str(n.get("name", "")).lower() == target_id.lower():
                PENDING_COMMANDS[n["ip"]] = {"command": command, "cmd_id": cmd_id, "time": time.time()}
                PENDING_COMMANDS[str(n.get("name", "")).lower()] = {"command": command, "cmd_id": cmd_id, "time": time.time()}
                target_name = n.get("name", n["ip"])
                found = True
                break
        if not found:
            PENDING_COMMANDS[target_id] = {"command": command, "cmd_id": cmd_id, "time": time.time()}
    return cmd_id, target_name

# =========================================================================
#  HTTP SERVER: STEALTH OUTBOUND AGENT RECEIVER & COMMAND DISPATCHER
# =========================================================================

class StealthAgentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            length = int(self.headers.get('content-length', 0))
            raw = self.rfile.read(length).decode('utf-8')
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}

        if path == "/heartbeat":
            self.handle_heartbeat(data)
        elif path == "/command_result":
            self.handle_command_result(data)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_heartbeat(self, data):
        client_ip = data.get("ip") or self.client_address[0]
        raw_name = data.get("name", f"RDP-{client_ip}")
        folder = data.get("folder", "RDP").strip().capitalize()
        uuid = data.get("uuid", "-")
        ram = data.get("ram", "-")
        status = data.get("status", "running")
        uptime = data.get("uptime", "-")

        assigned_name = raw_name

        with NODES_LOCK:
            nodes = load_nodes()
            matched_node = None
            for n in nodes:
                if n.get("ip") == client_ip:
                    matched_node = n
                    break
            
            if matched_node:
                # Update existing
                matched_node["last_seen"] = int(time.time())
                if ram != "-": matched_node["ram"] = ram
                if uuid != "-" and "sdk-node" in uuid: matched_node["uuid"] = uuid
                if status: matched_node["status"] = status
                if uptime != "-": matched_node["uptime"] = uptime
                assigned_name = matched_node.get("name", raw_name)
            else:
                # New RDP registering!
                # Auto-name if default name
                if not raw_name or raw_name.startswith("RDP-") or raw_name.startswith(f"{folder}-WIN-"):
                    assigned_name = get_next_worker_name(folder)
                else:
                    assigned_name = raw_name

                nodes.append({
                    "ip": client_ip,
                    "name": assigned_name,
                    "folder": folder,
                    "uuid": uuid,
                    "ram": ram,
                    "status": status,
                    "uptime": uptime,
                    "os": "Windows",
                    "last_seen": int(time.time())
                })
            save_nodes(nodes)

        # Check pending command
        cmd_to_dispatch = None
        cmd_id = None
        if client_ip in PENDING_COMMANDS:
            c = PENDING_COMMANDS.pop(client_ip)
            cmd_to_dispatch, cmd_id = c["command"], c["cmd_id"]
        elif assigned_name.lower() in PENDING_COMMANDS:
            c = PENDING_COMMANDS.pop(assigned_name.lower())
            cmd_to_dispatch, cmd_id = c["command"], c["cmd_id"]

        response_obj = {"status": "ok", "assigned_name": assigned_name}
        if cmd_to_dispatch:
            response_obj["command"] = cmd_to_dispatch
            response_obj["cmd_id"] = cmd_id

        resp_bytes = json.dumps(response_obj).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)

    def handle_command_result(self, data):
        ip = data.get("ip", "unknown")
        name = data.get("name", ip)
        cmd = data.get("cmd", "")
        status = data.get("status", "")

        cmd_indonesia = {
            "reboot": "REBOOT WINDOWS",
            "restart_earnapp": "RESTART EARNAPP"
        }.get(cmd, cmd.upper())

        notif_text = (
            f"⚡ <b>[KOMANDO DIEKSEKUSI]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ <b>Worker:</b> <b>{html.escape(name)}</b> (<code>{html.escape(ip)}</code>)\n"
            f"⚙️ <b>Aksi:</b> <code>{cmd_indonesia}</code>\n"
            f"📊 <b>Status:</b> <b>{html.escape(status.upper())}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        send_message(ADMIN_CHAT_ID, notif_text)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        return  # Silent logging

def run_http_server():
    try:
        server = HTTPServer(("0.0.0.0", HTTP_PORT), StealthAgentHandler)
        print(f"[HTTP SERVER] Stealth Agent Listener active on 0.0.0.0:{HTTP_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP SERVER ERROR] {e}")

# =========================================================================
#  TELEGRAM UI & DASHBOARD ENGINE
# =========================================================================

def render_dashboard(active_folder=None):
    nodes = load_nodes()
    now_ts = int(time.time())
    now_str = time.strftime("%H:%M:%S")
    master_ip = get_master_public_ip()

    if not nodes:
        setup_cmd = f"& ([scriptblock]::Create((irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1))) -MasterIP {master_ip} -Folder RDP"
        text = (
            "🚀 <b>EARNAPP WINDOWS RDP FLEET CONTROLLER</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 <b>Arsitektur:</b> Outbound Stealth Agent (0 Port Terbuka)\n\n"
            "⚠️ <i>Belum ada Windows RDP yang terhubung.</i>\n\n"
            "<b>Cara Menghubungkan RDP Pertama Anda (5 Detik):</b>\n"
            "1. Buka <b>PowerShell (Run as Admin)</b> di RDP Anda.\n"
            "2. Paste perintah 1-klik di bawah lalu Enter:\n\n"
            f"<code>{setup_cmd}</code>\n\n"
            "3. Langsung tutup RDP! RDP akan otomatis muncul di sini."
        )
        markup = {"inline_keyboard": [
            [{"text": "➕ Petunjuk Setup RDP", "callback_data": "btn_add"}],
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
        uptime = n.get("uptime", "-")
        last_seen = n.get("last_seen", 0)
        
        diff_sec = now_ts - last_seen if last_seen > 0 else 9999
        is_online = diff_sec <= 60  # Heartbeat tiap 15s
        if is_online: online_count += 1

        f_entry = folders_data.setdefault(f, {"nodes": [], "online": 0})
        f_entry["nodes"].append(n)
        if is_online: f_entry["online"] += 1

        status_emoji = "🟢" if is_online else "🟡" if diff_sec <= 300 else "🔴"
        seen_str = "Online" if diff_sec <= 30 else f"{int(diff_sec/60)}m lalu" if diff_sec < 3600 else f"{int(diff_sec/3600)}j lalu"
        
        claim_link = f"https://earnapp.com/r/{uuid}" if uuid != "-" and "sdk-node" in uuid else "<i>Belum klaim</i>"
        
        line = (
            f"{status_emoji} <b>{html.escape(str(name))}</b> (<code>{html.escape(str(ip))}</code>)\n"
            f"   ├ 💾 RAM: <code>{html.escape(str(ram))}</code> | 🕒 Seen: <i>{seen_str}</i>\n"
            f"   ├ ⏱️ Uptime: <code>{html.escape(str(uptime))}</code>\n"
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
            f"🔒 <b>Keamanan:</b> 0 Port Terbuka (Stealth Agent 15s)\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        text = header + "\n\n".join(f_lines)
        
        buttons = [
            [{"text": "🔄 Refresh", "callback_data": f"fld_ref_{matched_folder}"}, {"text": f"➕ Tambah ke {matched_folder}", "callback_data": f"fld_add_{matched_folder}"}],
            [{"text": "🔙 Semua Folder", "callback_data": "fld_MAIN"}, {"text": "🌐 Lihat Semua RDP", "callback_data": "fld_ALL"}],
            [{"text": "📋 List Node ID", "callback_data": "btn_ids"}, {"text": "🗑️ Hapus RDP", "callback_data": "btn_del_menu"}]
        ]
        
        # Quick action reboot buttons
        if f_nodes:
            reb_row = []
            for item in f_nodes[:3]:
                reb_row.append({"text": f"🔄 Reboot {item.get('name')}", "callback_data": f"reb_{item.get('ip')}"})
            buttons.insert(1, reb_row)

        return text, {"inline_keyboard": buttons}

    # VIEW 2: Semua worker sekaligus
    elif active_folder == "ALL":
        header = (
            f"⚡ <b>EARNAPP WINDOWS RDP DASHBOARD (ALL)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ <b>Total RDP:</b> {online_count}/{total_nodes} Online\n"
            f"🔒 <b>Port Terbuka:</b> 0 Port (100% Aman)\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code>\n"
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
            f"🔒 <b>Arsitektur:</b> Outbound Stealth Agent (0 Port Terbuka)\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code>\n"
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
        master_ip = get_master_public_ip()

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
            folder_target = parts[1].strip().capitalize() if len(parts) >= 2 else "RDP"
            next_name = get_next_worker_name(folder_target)
            setup_cmd = f"& ([scriptblock]::Create((irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1))) -MasterIP {master_ip} -Folder {folder_target}"

            msg_text = (
                f"➕ <b>SETUP RDP KE FOLDER {html.escape(folder_target.upper())} (CARA 2: STEALTH):</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 <b>Keamanan 100% Anti-Curiga:</b>\n"
                f"• Port 22 tetap <b>MATI TOTAL</b>.\n"
                f"• 0 Port Masuk dibuka (Penyedia RDP tidak akan tahu!).\n"
                f"• Nama worker otomatis urut: <b>{html.escape(next_name)}</b>\n\n"
                f"⚡ <b>Langkah Cepat (Hanya 5 Detik):</b>\n"
                f"1. Buka RDP Anda.\n"
                f"2. Buka <b>PowerShell (Run as Administrator)</b>.\n"
                f"3. Copy & paste perintah 1-baris berikut, lalu tekan Enter:\n\n"
                f"<code>{setup_cmd}</code>\n\n"
                f"4. <b>Langsung tutup RDP!</b> Anda tidak perlu menunggu di layarnya.\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ <i>RDP otomatis mengirim link klaim ke sini dan siap dikontrol via Telegram!</i>"
            )
            markup = {"inline_keyboard": [
                [{"text": "🔙 Batal / Dashboard", "callback_data": "btn_refresh"}]
            ]}
            send_message(chat_id, msg_text, reply_markup=markup)
        elif text.startswith("/reboot"):
            parts = text.split()
            if len(parts) >= 2:
                target = parts[1].strip()
                cmd_id, target_name = queue_command(target, "reboot")
                send_message(
                    chat_id,
                    f"⏳ <b>Perintah REBOOT dikirim ke antrean RDP [ {html.escape(target_name)} ]!</b>\n\n"
                    f"RDP akan otomatis restart dalam <b>~15 detik</b> saat sinyal heartbeat berikutnya diterima.\n"
                    f"<i>(0 Port Terbuka, 100% Aman & Stealth).</i>"
                )
            else:
                send_message(chat_id, "Gunakan: <code>/reboot &lt;nama_atau_ip&gt;</code> (Contoh: <code>/reboot nayla-1</code>)")
        elif text.startswith("/restart"):
            parts = text.split()
            if len(parts) >= 2:
                target = parts[1].strip()
                cmd_id, target_name = queue_command(target, "restart_earnapp")
                send_message(
                    chat_id,
                    f"⏳ <b>Perintah RESTART EARNAPP dikirim ke antrean RDP [ {html.escape(target_name)} ]!</b>\n\n"
                    f"Proses EarnApp akan direstart dalam <b>~15 detik</b>."
                )
            else:
                send_message(chat_id, "Gunakan: <code>/restart &lt;nama_atau_ip&gt;</code> (Contoh: <code>/restart nayla-1</code>)")
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
                nodes = load_nodes()
                buttons = [[{"text": f"🗑️ {n.get('name')} ({n.get('ip')})", "callback_data": f"del_{n.get('ip')}"}] for n in nodes]
                buttons.append([{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}])
                send_message(chat_id, "🗑️ <b>PILIH RDP YANG AKAN DIHAPUS:</b>", reply_markup={"inline_keyboard": buttons})
        elif text.startswith("/help") or "help" in text_lower:
            help_text = (
                "📖 <b>PANDUAN BOT RDP FLEET CONTROLLER (STEALTH AGENT)</b>\n\n"
                "• <code>/start</code> - Buka ringkasan folder dashboard RDP\n"
                "• <code>/add [folder]</code> - Dapatkan perintah 1-klik untuk hubungkan RDP\n"
                "• <code>/reboot &lt;nama/ip&gt;</code> - Restart Windows RDP secara remote (15s)\n"
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
        master_ip = get_master_public_ip()

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
            setup_cmd = f"& ([scriptblock]::Create((irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1))) -MasterIP {master_ip} -Folder {target_f}"
            msg_text = (
                f"➕ <b>TAMBAH RDP KE FOLDER {html.escape(target_f.upper())}:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Worker berikutnya otomatis dinamai: <b>{html.escape(next_name)}</b>\n"
                f"🔒 <b>0 Port Terbuka</b> (Penyedia RDP tidak akan tahu!)\n\n"
                f"1. Buka <b>PowerShell (Admin)</b> di RDP baru Anda.\n"
                f"2. Paste perintah 1-klik ini:\n\n"
                f"<code>{setup_cmd}</code>\n\n"
                f"3. Langsung tutup RDP! RDP akan langsung muncul di folder ini."
            )
            edit_message(chat_id, msg_id, msg_text, {"inline_keyboard": [[{"text": "🔙 Batal", "callback_data": f"fld_view_{target_f}"}]]})
        elif data.startswith("reb_"):
            target_ip = data.replace("reb_", "")
            cmd_id, target_name = queue_command(target_ip, "reboot")
            answer_callback(cb_id, f"Perintah reboot dikirim ke {target_name}. RDP akan restart dalam ~15s!", show_alert=True)
        elif data == "btn_add":
            answer_callback(cb_id)
            setup_cmd = f"& ([scriptblock]::Create((irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1))) -MasterIP {master_ip} -Folder RDP"
            msg_text = (
                "➕ <b>SETUP 1-KLIK WINDOWS RDP (STEALTH AGENT):</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🔒 <b>Keamanan 100% Anti-Curiga:</b>\n"
                "• Port 22 tetap <b>MATI TOTAL</b>.\n"
                "• 0 Port Masuk yang dibuka di RDP Anda.\n"
                "• Menggunakan Outbound Agent (Trafik seperti web browsing biasa).\n\n"
                "⚡ <b>Langkah Cepat (Hanya 5 Detik):</b>\n"
                "1. Buka <b>PowerShell (Run as Admin)</b> di RDP Anda.\n"
                "2. Paste perintah otomatis berikut lalu Enter:\n\n"
                f"<code>{setup_cmd}</code>\n\n"
                "3. Langsung tutup RDP! Script akan otomatis mendaftarkan RDP ke bot ini."
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
#  TELEGRAM POLLING DAEMON
# =========================================================================

def telegram_poller():
    offset = 0
    print("[INIT] RDP Telegram Polling engine running.")
    try:
        flush = tg_call("getUpdates", {"offset": -1, "timeout": 1}, timeout=5)
        if flush and flush.get("ok") and flush.get("result"):
            offset = flush["result"][-1]["update_id"] + 1
    except Exception: pass

    try:
        master_ip = get_master_public_ip()
        startup_msg = (
            "🤖 <b>EarnApp Windows RDP Master Bot Aktif!</b>\n\n"
            "✅ <b>Arsitektur:</b> Outbound Stealth Agent (0 Port Terbuka)\n"
            f"🌐 <b>Master IP:</b> <code>{master_ip}</code>\n"
            "🛡️ <b>Remote Reboot & Restart:</b> Ready (Polling 15s)\n\n"
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
