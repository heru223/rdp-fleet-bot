#!/usr/bin/env python3
"""
EarnApp Windows RDP Fleet Master Controller Bot
- Dedicated Telegram Bot for Windows RDP fleet management
- Folder & grouping system
- Node ID & Claim URL tracker
- Instant Telegram UI with interactive inline keyboards
- Lightweight HTTP registration / heartbeat listener (port 9090)
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
                            res.append({"ip": k, "name": v.get("name", k), "uuid": v.get("uuid", "-"), "folder": v.get("folder", "RDP"), "ram": v.get("ram", "-"), "last_seen": v.get("last_seen", 0)})
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
                "os": n.get("os", "Windows"),
                "last_seen": n.get("last_seen", int(time.time()))
            }
        with open(NODES_FILE, "w", encoding="utf-8") as f:
            json.dump(dict_format, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Save nodes failed: {e}")

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

def get_node_folder(n):
    f = n.get("folder", "")
    if f and f.strip(): return f.strip().capitalize()
    name = n.get("name", "")
    m = re.match(r'^([a-zA-Z]+)', name)
    if m:
        pref = m.group(1).capitalize()
        if pref.lower() not in ["rdp", "win", "worker"]: return pref
    return "RDP"

def get_all_folders():
    nodes = load_nodes()
    folders = {}
    for n in nodes:
        f = get_node_folder(n)
        folders.setdefault(f, []).append(n)
    sorted_names = sorted(folders.keys(), key=lambda x: (x.lower() == "rdp", x.lower()))
    return {k: folders[k] for k in sorted_names}

def render_dashboard(active_folder=None):
    nodes = load_nodes()
    now_ts = int(time.time())
    now_str = time.strftime("%H:%M:%S")

    if not nodes:
        text = (
            "🚀 <b>EARNAPP WINDOWS RDP FLEET CONTROLLER</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <i>Belum ada Windows RDP yang terdaftar.</i>\n\n"
            "<b>Cara Menghubungkan RDP:</b>\n"
            "Buka PowerShell di Windows RDP Anda, lalu paste perintah ini:\n"
            "<code>irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex</code>"
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
        last_seen = n.get("last_seen", 0)
        
        # Online jika last_seen < 30 menit atau terdaftar
        diff_min = int((now_ts - last_seen) / 60) if last_seen > 0 else 999
        is_online = diff_min <= 30
        if is_online: online_count += 1

        f_entry = folders_data.setdefault(f, {"nodes": [], "online": 0})
        f_entry["nodes"].append(n)
        if is_online: f_entry["online"] += 1

        status_emoji = "🟢" if is_online else "🟡" if diff_min <= 120 else "🔴"
        seen_str = "Online (Aktif)" if diff_min <= 5 else f"{diff_min}m lalu" if diff_min < 60 else f"{int(diff_min/60)}j lalu"
        
        claim_link = f"https://earnapp.com/r/{uuid}" if uuid != "-" and "sdk-node" in uuid else "<i>Belum klaim</i>"
        
        line = (
            f"{status_emoji} <b>{html.escape(str(name))}</b> (<code>{html.escape(str(ip))}</code>)\n"
            f"   ├ 💾 RAM: <code>{html.escape(str(ram))}</code> | 🕒 Seen: <i>{seen_str}</i>\n"
            f"   ├ 🆔 <code>{html.escape(str(uuid[:22]))}...</code>\n"
            f"   └ 🔗 {claim_link}"
        )
        node_lines.append((f, line))

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
        f_lines = [l for (f, l) in node_lines if f == matched_folder]
        header = (
            f"📁 <b>FOLDER RDP: {html.escape(matched_folder.upper())}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ <b>Workers:</b> {f_info['online']}/{len(f_info['nodes'])} Online\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code> | 🛡️ <b>RDP Keep-Alive:</b> 🟢 24/7\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        text = header + "\n\n".join(f_lines)
        markup = {
            "inline_keyboard": [
                [{"text": "🔄 Refresh", "callback_data": f"fld_ref_{matched_folder}"}, {"text": "🔙 Semua Folder", "callback_data": "fld_MAIN"}],
                [{"text": "🌐 Lihat Semua RDP", "callback_data": "fld_ALL"}, {"text": "➕ Setup RDP Baru", "callback_data": "btn_add"}],
                [{"text": "📋 List Node ID", "callback_data": "btn_ids"}, {"text": "🗑️ Hapus RDP", "callback_data": "btn_del_menu"}]
            ]
        }
        return text, markup

    # VIEW 2: Semua worker sekaligus
    elif active_folder == "ALL":
        header = (
            f"⚡ <b>EARNAPP WINDOWS RDP DASHBOARD (ALL)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ <b>Total RDP:</b> {online_count}/{total_nodes} Online\n"
            f"🕒 <b>Update:</b> <code>{now_str}</code> | 🛡️ <b>24/7 Keep-Alive:</b> 🟢\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        text = header + "\n\n".join([l for (f, l) in node_lines])
        markup = {
            "inline_keyboard": [
                [{"text": "📁 Mode Ringkasan Folder", "callback_data": "fld_MAIN"}, {"text": "🔄 Refresh", "callback_data": "fld_ALL"}],
                [{"text": "➕ Setup RDP Baru", "callback_data": "btn_add"}, {"text": "📋 List Node ID", "callback_data": "btn_ids"}],
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

def handle_telegram_message(msg):
    try:
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        if not text or not chat_id: return
        if int(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "⛔ <b>Akses Ditolak.</b>")
            return

        text_lower = text.lower()
        if any(text.startswith(cmd) for cmd in ["/start", "/menu", "/status", "/nodes", "/dashboard"]) or "status" in text_lower:
            dash_text, markup = render_dashboard()
            res = send_message(chat_id, dash_text, markup)
            if res and res.get("ok"):
                LAST_DASHBOARD_MSG["chat_id"] = chat_id
                LAST_DASHBOARD_MSG["message_id"] = res["result"]["message_id"]
                LAST_DASHBOARD_MSG["view"] = None
        elif text.startswith("/refresh") or "refresh" in text_lower:
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
        elif text.startswith("/folder"):
            parts = text.split()
            f_target = parts[1].strip() if len(parts) >= 2 else None
            dash_text, markup = render_dashboard(active_folder=f_target)
            res = send_message(chat_id, dash_text, markup)
            if res and res.get("ok"):
                LAST_DASHBOARD_MSG["chat_id"] = chat_id
                LAST_DASHBOARD_MSG["message_id"] = res["result"]["message_id"]
                LAST_DASHBOARD_MSG["view"] = f_target
        elif text.startswith("/add") or "tambah rdp" in text_lower or "setup rdp" in text_lower:
            parts = text.split()
            if len(parts) >= 3:
                ip = parts[1].strip()
                name = parts[2].strip()
                folder = parts[3].strip().capitalize() if len(parts) >= 4 else "RDP"
                uuid = parts[4].strip() if len(parts) >= 5 else "-"
                
                with NODES_LOCK:
                    nodes = load_nodes()
                    updated = False
                    for n in nodes:
                        if n.get("ip") == ip or n.get("name") == name:
                            n["ip"] = ip
                            n["name"] = name
                            n["folder"] = folder
                            if uuid != "-": n["uuid"] = uuid
                            n["last_seen"] = int(time.time())
                            updated = True
                            break
                    if not updated:
                        nodes.append({"ip": ip, "name": name, "folder": folder, "uuid": uuid, "ram": "-", "last_seen": int(time.time())})
                    save_nodes(nodes)
                
                send_message(chat_id, f"✅ RDP <b>{html.escape(name)}</b> (<code>{html.escape(ip)}</code>) berhasil didaftarkan ke folder <b>{html.escape(folder)}</b>!", reply_markup={"inline_keyboard": [[{"text": "📊 Dashboard", "callback_data": "btn_refresh"}]]})
            else:
                setup_cmd = "irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex"
                msg_text = (
                    "➕ <b>CARA HUBUNGKAN WINDOWS RDP:</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "1. Buka <b>PowerShell (Run as Administrator)</b> di Windows RDP Anda.\n"
                    "2. Copy dan jalankan perintah 1-klik berikut:\n\n"
                    f"<code>{setup_cmd}</code>\n\n"
                    "3. RDP akan otomatis dikonfigurasi (Anti-Sleep, 24/7 Keep-Alive, Auto-Reboot 24h) dan otomatis melapor ke bot ini!\n\n"
                    "<i>Atau tambah manual:</i>\n"
                    "<code>/add &lt;ip&gt; &lt;nama&gt; [folder] [node_id]</code>"
                )
                send_message(chat_id, msg_text, reply_markup={"inline_keyboard": [[{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}]]})
        elif text.startswith("/id") or "list id" in text_lower or "node id" in text_lower:
            nodes = load_nodes()
            lines = ["📋 <b>EARNAPP RDP NODE IDs & CLAIM URL</b>\n━━━━━━━━━━━━━━━━━━━━━"]
            for n in nodes:
                ip, name, uuid = n.get("ip"), n.get("name", n.get("ip")), n.get("uuid", "-")
                claim = f"https://earnapp.com/r/{uuid}" if uuid != "-" and "sdk-node" in uuid else "<i>Belum terdeteksi</i>"
                lines.append(f"🏷️ <b>{html.escape(str(name))}</b> [📁 {get_node_folder(n)}] (<code>{html.escape(str(ip))}</code>)\n🆔 <code>{html.escape(str(uuid))}</code>\n🔗 {claim}\n")
            send_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": [[{"text": "🔙 Kembali ke Dashboard", "callback_data": "btn_refresh"}]]})
        elif text.startswith("/rename") or "rename" in text_lower:
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
        elif text.startswith("/move") or "pindah folder" in text_lower:
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
        elif text.startswith("/del"):
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
                send_message(chat_id, "Gunakan: <code>/del &lt;ip atau nama&gt;</code>")
        elif text.startswith("/help") or "help" in text_lower:
            help_text = (
                "📖 <b>PANDUAN BOT RDP FLEET CONTROLLER</b>\n\n"
                "• <code>/start</code> - Buka ringkasan folder dashboard RDP\n"
                "• <code>/folder &lt;nama&gt;</code> - Buka folder tertentu (misal: <code>/folder Singapore</code>)\n"
                "• <code>/all</code> - Tampilkan semua Windows RDP\n"
                "• <code>/refresh</code> - Update status live\n"
                "• <code>/add &lt;ip&gt; &lt;nama&gt; [folder] [uuid]</code> - Tambah/daftar RDP manual\n"
                "• <code>/move &lt;nama&gt; &lt;folder&gt;</code> - Pindah folder\n"
                "• <code>/rename &lt;lama&gt; &lt;baru&gt;</code> - Ganti nama RDP\n"
                "• <code>/del &lt;ip/nama&gt;</code> - Hapus RDP dari daftar\n"
                "• <code>/ids</code> - List semua Node ID & Claim URL EarnApp"
            )
            send_message(chat_id, help_text)
    except Exception as e:
        print(f"[MSG ERROR] {e}")

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
        elif data == "btn_add":
            answer_callback(cb_id)
            setup_cmd = "irm https://raw.githubusercontent.com/heru223/rdp-fleet-bot/main/setup.ps1 | iex"
            msg_text = (
                "➕ <b>SETUP 1-KLIK WINDOWS RDP:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1. Buka <b>PowerShell</b> di Windows RDP Anda.\n"
                "2. Jalankan perintah otomatis berikut:\n\n"
                f"<code>{setup_cmd}</code>\n\n"
                "Script akan otomatis membaca Node ID, mengaktifkan Anti-Sleep & Keep-Alive, lalu mendaftarkan RDP ke bot ini!"
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

# HTTP Registration Receiver for RDP Agents
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
                    nodes.append({"ip": ip, "name": name, "folder": folder, "uuid": uuid, "ram": ram, "os": os_name, "last_seen": int(time.time())})
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
            "🛡️ <b>24/7 Keep-Alive & Watchdog:</b> Ready\n\n"
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
