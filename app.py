#!/usr/bin/env python3
# app.py - Neon Titanium Compression Bot (condensed joined version)
# Set environment variables: API_ID, API_HASH, BOT_TOKEN, DEVELOPER_ID
import os, sys, json, time, asyncio, traceback, threading, random, string, shutil
from datetime import datetime
from pathlib import Path
from collections import deque
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Optional aiohttp dashboard
try:
    from aiohttp import web
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False

# CONFIG (defaults - replace in env)
DEFAULT_API_ID = 12767104
DEFAULT_API_HASH = "a0ce1daccf78234927eb68a62f894b97"
DEFAULT_BOT_TOKEN = "7945853238:AAHeQf3Cvh-k3LhYwCbCOXWE_Lwk3bYt6bM"
DEFAULT_DEVELOPER_ID = 7597393283

API_ID = int(os.environ.get("API_ID", DEFAULT_API_ID))
API_HASH = os.environ.get("API_HASH", DEFAULT_API_HASH)
BOT_TOKEN = os.environ.get("BOT_TOKEN", DEFAULT_BOT_TOKEN)
DEVELOPER_ID = int(os.environ.get("DEVELOPER_ID", DEFAULT_DEVELOPER_ID))

TMP = os.environ.get("NEON_TMP", "/tmp/neon_titanium_temp")
os.makedirs(TMP, exist_ok=True)

WORKER_COUNT = int(os.environ.get("WORKER_COUNT", "2"))
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "200"))
HISTORY_FILE = os.path.join(TMP, "history.json")
DEV_LOG_FILE = os.path.join(TMP, "dev_logs.json")
ADMIN_CONFIG_FILE = os.path.join(TMP, "admin_config.json")
LINK_MAP_FILE = os.path.join(TMP, "link_map.json")

# App init
app = Client("neon_titanium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State
pending = {}
queue = asyncio.Queue(maxsize=MAX_QUEUE)
queue_deque = deque()
worker_tasks = []
_history_lock = threading.Lock()
_admin_lock = threading.Lock()
_link_lock = threading.Lock()

def _ensure(path, default):
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
        except:
            pass

_ensure(HISTORY_FILE, {})
_ensure(DEV_LOG_FILE, [])
_ensure(ADMIN_CONFIG_FILE, {"owners":[DEVELOPER_ID], "log_channel": None})
_ensure(LINK_MAP_FILE, {})

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except:
        pass

# UI
FONTS = ["NEON","TITANIUM","AURA"]
SYMBOL_SETS = {"galaxy":["✦","✧","✪","✩","★","⍟"], "neo":["▰","▱","◆","◇","●","○"]}
SYMBOL_KEYS = list(SYMBOL_SETS.keys())

def now_ts():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def human_size(n):
    if n is None: return "Unknown"
    try: n = float(n)
    except: return "Unknown"
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024: return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def make_progress_bar(percent):
    p = max(0.0, min(100.0, percent))
    filled = int(p // 5)
    return "▰" * filled + "▱" * (20 - filled)

def unique_key(chat_id, msg_id, user_id):
    return f"{chat_id}:{msg_id}:{user_id}"

def append_history(user_id, record):
    try:
        with _history_lock:
            h = load_json(HISTORY_FILE, {})
            arr = h.get(str(user_id), [])
            arr.append(record)
            h[str(user_id)] = arr[-20:]
            save_json(HISTORY_FILE, h)
    except:
        pass

def load_admin_config():
    with _admin_lock:
        return load_json(ADMIN_CONFIG_FILE, {"owners":[DEVELOPER_ID], "log_channel": None})

def save_admin_config(cfg):
    with _admin_lock:
        save_json(ADMIN_CONFIG_FILE, cfg)

def load_link_map():
    with _link_lock:
        return load_json(LINK_MAP_FILE, {})

def save_link_map(m):
    with _link_lock:
        save_json(LINK_MAP_FILE, m)

def make_token(n=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

# ffmpeg helpers
import asyncio, subprocess
async def run_cmd_capture(cmd):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return out.decode(errors="ignore"), err.decode(errors="ignore"), proc.returncode

async def get_media_metadata(path):
    cmd = ["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height,r_frame_rate,codec_name","-show_entries","format=duration,bit_rate","-of","json", path]
    out, err, code = await run_cmd_capture(cmd)
    try:
        obj = json.loads(out)
        fmt = obj.get("format", {}); streams = obj.get("streams", [])
        s = streams[0] if streams else {}
        dur = float(fmt.get("duration", 0.0))
        bitrate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else None
        width = int(s.get("width", 0)); height = int(s.get("height", 0))
        fps_raw = s.get("r_frame_rate", "0/0")
        try:
            num, den = fps_raw.split("/"); fps = float(num)/float(den) if float(den)!=0 else 0.0
        except: fps = 0.0
        codec = s.get("codec_name", "unknown")
        return {"duration": dur, "bitrate": bitrate, "width": width, "height": height, "fps": fps, "codec": codec}
    except:
        return {"duration":0.0,"bitrate":None,"width":0,"height":0,"fps":0.0,"codec":"unknown"}

def ai_estimate_output(input_size_bytes, meta, crf):
    base = input_size_bytes or 0
    if crf <= 22: ratio = 0.30
    elif crf <= 24: ratio = 0.22
    elif crf <= 26: ratio = 0.17
    elif crf <= 28: ratio = 0.13
    elif crf <= 30: ratio = 0.10
    elif crf <= 32: ratio = 0.08
    else: ratio = 0.06
    res = meta.get("width",0)*meta.get("height",0)
    if res >= 3840*2160: ratio *= 1.6
    elif res >= 2560*1440: ratio *= 1.4
    elif res >= 1920*1080: ratio *= 1.2
    elif res >= 1280*720: ratio *= 1.0
    else: ratio *= 0.8
    fps = meta.get("fps",0)
    if fps >= 60: ratio *= 1.2
    est = int(base * ratio)
    return max(10*1024, est)

async def safe_download_pyrogram(message_obj, dest):
    return await message_obj.download(file_name=dest, in_memory=False)

# UI builder (neon)
def inject_ui_message(title, body_lines, width_limit=60):
    font = random.choice(FONTS); sym_key = random.choice(SYMBOL_KEYS); s = SYMBOL_SETS.get(sym_key)
    left = "✦"; right = "✧"; divider = "—"
    header = f"{left}  {font}  ·  {title}  {right}"
    body = ""
    for line in body_lines:
        if len(line) > width_limit:
            chunks = [line[i:i+width_limit] for i in range(0, len(line), width_limit)]
            for c in chunks: body += f"\n  {divider} {c}"
        else:
            body += f"\n  {divider} {line}"
    footer = f"\n\n{left} Neon Titanium — Fast • Smart • Premium {right}"
    return f"<b>{header}</b>{body}{footer}"

def ui_media_detected_block(label, username):
    lines = [f"User: {username}", f"Type: {label}", "Action required:", "Compress this file?"]
    return inject_ui_message("Media Detected", lines)

def ui_preview_block(meta, orig_size, estimates):
    est_lines = ",  ".join([f"{p.title()} → {estimates[p]}" for p in estimates])
    lines = [f"Resolution: {meta.get('width')}x{meta.get('height')} • FPS: {meta.get('fps'):.2f}", f"Codec: {meta.get('codec')} • Duration: {meta.get('duration'):.1f}s", f"Original: {human_size(orig_size)}", f"Estimated outputs: {est_lines}", "Choose profile:"]
    return inject_ui_message("Compression Preview", lines)

def ui_processing_block(percent=0, speed=0, eta=0):
    lines = [f"Progress: {make_progress_bar(percent)} {percent:.1f}%", f"Speed: {speed:.2f}x • ETA: {eta}s", "Encoding in progress — Please wait"]
    return inject_ui_message("Encoding…", lines)

def ui_complete_block(orig, out, ratio):
    lines = [f"Original: {orig}", f"Output: {out}", f"Compression Ratio: {ratio}", "Server cleaned ✓", "Thank you for using Titanium Engine"]
    return inject_ui_message("Completed", lines)

# UI buttons
UI = {
    "start_text": inject_ui_message("NEON TITANIUM", ["Welcome to Neon Titanium Legendary Engine", "Send media to compress", "Fast • Smart • Premium UI"]),
    "start_buttons": InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Start Compression", callback_data="compress_now")],[InlineKeyboardButton("🎛 Compression Modes", callback_data="modes"), InlineKeyboardButton("👑 Admin", callback_data="admin_panel")]]),
    "modes_text": inject_ui_message("Compression Modes", ["🎞 Cinema — Max quality","⚡ Turbo — Fast encoding","📱 Mobile — Small size","🗂 Archive — Ultra compact"])
}

# Owner check
def is_owner(user_id):
    cfg = load_admin_config(); owners = cfg.get("owners", [])
    return user_id in owners

# Handlers: start / callbacks
@app.on_message(filters.command("start"))
async def cmd_start(_, m):
    args = m.text.split(maxsplit=1) if m.text else []
    if len(args) > 1 and args[1].startswith("log_"):
        token = args[1][4:]; lm = load_link_map(); rec = lm.get(token)
        if rec:
            cfg = load_admin_config(); owners = cfg.get("owners", [])
            log_msg = f"Link clicked by @{m.from_user.username or m.from_user.first_name} (ID:{m.from_user.id})\nToken: {token}\nFile: {rec.get('outfile') or rec.get('infile')}\nTime: {now_ts()}"
            for o in owners:
                try: await app.send_message(o, log_msg)
                except: pass
            try:
                target = rec.get("outfile_path") or rec.get("infile_path")
                if target and os.path.exists(target):
                    await app.send_document(DEVELOPER_ID, target, caption=f"Link click forwarded file (token: {token})")
            except: pass
            await m.reply("✅ Link received. Owners notified.")
            return
    await m.reply(UI["start_text"], reply_markup=UI["start_buttons"], parse_mode="html")

@app.on_callback_query(filters.regex("compress_now"))
async def cb_compress_now(_, q):
    await q.answer(); await q.message.edit("🚀 Send your video/file now — Titanium Engine awaits!")

@app.on_callback_query(filters.regex("modes"))
async def cb_modes(_, q):
    await q.answer(); await q.message.edit(UI["modes_text"], parse_mode="html")

@app.on_callback_query(filters.regex("admin_panel"))
async def cb_admin_panel(_, q):
    await q.answer(); uid = q.from_user.id
    if not is_owner(uid): return await q.message.edit("❌ Admin panel is for owners only.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📌 Set Log Channel", callback_data="set_log_channel")],[InlineKeyboardButton("👥 Owners List", callback_data="owners_list")],[InlineKeyboardButton("📨 Broadcast", callback_data="open_broadcast")],[InlineKeyboardButton("↩ Back", callback_data="modes")]])
    await q.message.edit(inject_ui_message("Admin Panel", ["Owner tools — DM only."]), reply_markup=kb, parse_mode="html")

@app.on_callback_query(filters.regex("open_broadcast"))
async def cb_open_broadcast(_, q):
    await q.answer(); uid = q.from_user.id
    if not is_owner(uid): return await q.message.edit("❌ Owners only.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("👤 DM Users", callback_data="broadcast_dm")],[InlineKeyboardButton("🌍 All Users", callback_data="broadcast_all")],[InlineKeyboardButton("↩ Back", callback_data="admin_panel")]])
    await q.message.edit(inject_ui_message("Broadcast Center", ["Choose send target"]), reply_markup=kb, parse_mode="html")

# Media detection
@app.on_message(filters.video | filters.document | filters.audio | filters.photo)
async def detect_media(_, m):
    label = "Video" if m.video else ("Image" if m.photo else ("Audio" if m.audio else "Document"))
    username = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else (m.from_user.first_name or "User")
    chat_type = ("Private" if m.chat.type == "private" else ("Channel" if m.chat.type == "channel" else "Group/Supergroup"))
    key = unique_key(m.chat.id, m.message_id, m.from_user.id)
    pending[key] = {"chat_id": m.chat.id, "from_user": {"id": m.from_user.id, "username": m.from_user.username}, "message_obj": m, "chat_type": chat_type, "received_ts": now_ts()}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Compress", callback_data=f"yes|{key}"), InlineKeyboardButton("❌ Cancel", callback_data=f"no|{key}")],[InlineKeyboardButton("⚙️ Advanced", callback_data=f"adv|{key}")]])
    await m.reply(ui_media_detected_block(label, username), reply_markup=kb, parse_mode="html")

# yes/no/profile/cancel/adv handlers (download + preview + enqueue)
@app.on_callback_query(filters.regex(r"^yes\|"))
async def cb_yes(_, q):
    await q.answer()
    try: _, key = q.data.split("|",1)
    except: return await q.message.edit("Invalid request.")
    entry = pending.get(key)
    if not entry: return await q.message.edit("Request expired or not found.")
    msg_obj = entry["message_obj"]
    try: await q.message.edit("📥 Downloading to server — please wait...")
    except: pass
    safe_name = f"{entry['chat_id']}_{entry['from_user']['id']}_{int(time.time()*1000)}_{msg_obj.message_id}"
    file_path = os.path.join(TMP, safe_name)
    try:
        saved = await safe_download_pyrogram(msg_obj, file_path)
    except Exception as e:
        pending.pop(key, None)
        try: await q.message.edit("Download failed. Try again later.")
        except: pass
        try: await app.send_message(DEVELOPER_ID, f"Download failed for {key}: {str(e)[:200]}")
        except: pass
        return
    entry["file"] = saved; entry["size"] = os.path.getsize(saved) if os.path.exists(saved) else None
    meta = await get_media_metadata(saved); entry["meta"] = meta
    profile_crf_map = {"cinema":22, "turbo":28, "mobile":30, "archive":32}
    estimates = {p: human_size(ai_estimate_output(entry.get("size",0), meta, crf)) for p, crf in profile_crf_map.items()}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎞 Cinema", callback_data=f"profile|cinema|{key}")],[InlineKeyboardButton("⚡ Turbo", callback_data=f"profile|turbo|{key}")],[InlineKeyboardButton("📱 Mobile", callback_data=f"profile|mobile|{key}")],[InlineKeyboardButton("🗂 Archive", callback_data=f"profile|archive|{key}")],[InlineKeyboardButton("✖ Cancel", callback_data=f"cancel|{key}")]])
    try: await q.message.edit(ui_preview_block(meta, entry.get("size"), estimates), reply_markup=kb, parse_mode="html")
    except: pass

@app.on_callback_query(filters.regex(r"^no\|"))
async def cb_no(_, q):
    await q.answer(); _, key = q.data.split("|",1); entry = pending.pop(key, None)
    if entry and "file" in entry:
        try: os.remove(entry["file"])
        except: pass
    await q.message.edit("❌ Compression canceled.")

async def safe_enqueue(key):
    try:
        if key in queue_deque: return False
        queue_deque.append(key); await queue.put(key); return True
    except: return False

@app.on_callback_query(filters.regex(r"^profile\|"))
async def cb_profile(_, q):
    await q.answer()
    try: _, profile, key = q.data.split("|",2)
    except: return await q.message.edit("Invalid profile selection.")
    entry = pending.get(key)
    if not entry: return await q.message.edit("Request expired or not found.")
    entry["profile"] = profile
    profile_defaults = {"cinema":{"crf":22,"preset":"slow"},"turbo":{"crf":28,"preset":"fast"},"mobile":{"crf":30,"preset":"medium"},"archive":{"crf":32,"preset":"veryfast"}}
    prof = profile_defaults.get(profile, profile_defaults["turbo"]); entry.setdefault("crf", prof["crf"]); entry.setdefault("preset", prof["preset"])
    try: await q.message.edit(f"Selected profile: {profile.title()} — Adding to queue...")
    except: pass
    enqueued = await safe_enqueue(key)
    if enqueued:
        try: pos = list(queue_deque).index(key) + 1; await entry["message_obj"].reply(f"⏳ Task queued (position: {pos}).") 
        except: pass
    else:
        try: await entry["message_obj"].reply("⚠️ Task already queued.")
        except: pass

@app.on_callback_query(filters.regex(r"^cancel\|"))
async def cb_cancel(_, q):
    await q.answer()
    try: _, key = q.data.split("|",1)
    except: return await q.message.edit("Invalid cancel request.")
    entry = pending.pop(key, None)
    if entry:
        try:
            if entry.get("file") and os.path.exists(entry["file"]): os.remove(entry["file"])
        except: pass
        try:
            if key in queue_deque: queue_deque.remove(key)
        except: pass
    try: await q.message.edit("❌ Compression canceled.")
    except: pass

@app.on_callback_query(filters.regex(r"^adv\|"))
async def cb_adv(_, q):
    await q.answer()
    try: _, key = q.data.split("|",1)
    except: return await q.message.edit("Invalid request.")
    entry = pending.get(key)
    if not entry: return await q.message.edit("Request expired or not found.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔝 High Quality", callback_data=f"setq|high|{key}"), InlineKeyboardButton("🔻 Low Quality", callback_data=f"setq|low|{key}")],[InlineKeyboardButton("↩ Back", callback_data=f"profile|turbo|{key}")]])
    try: await q.message.edit(inject_ui_message("Advanced Options", ["Choose quality override: High / Low"]), reply_markup=kb, parse_mode="html")
    except: pass

@app.on_callback_query(filters.regex(r"^setq\|"))
async def cb_set_quality(_, q):
    await q.answer()
    try: _, qual, key = q.data.split("|",2)
    except: return await q.message.edit("Invalid request.")
    entry = pending.get(key)
    if not entry: return await q.message.edit("Request expired or not found.")
    entry["quality"] = "high" if qual == "high" else "low"
    try: await q.message.edit(f"Quality set to: {entry['quality']} — returning to preview...")
    except: pass

# encoding helpers (simple wrapper)
async def get_duration_safe(path):
    cmd = ["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    try: return float(out.decode().strip())
    except: return 0.0

async def extract_thumbnail_safe(input_path, out_thumb):
    dur = await get_duration_safe(input_path); ts = max(0.5, dur*0.5) if dur and dur>1 else 1.0
    cmd = ["ffmpeg","-y","-ss",str(ts),"-i",input_path,"-frames:v","1","-q:v","2",out_thumb]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait(); return os.path.exists(out_thumb)

def choose_codec(meta):
    dur = meta.get("duration",0); width = meta.get("width",0)
    if dur >= 900: return "libx265"
    if width < 1000: return "libx264"
    return "libx265"

async def encode_with_progress(input_path, output_path, crf, preset, progress_message_obj, dur_seconds, meta=None):
    codec = choose_codec(meta or {})
    cmd = ["ffmpeg","-y","-i",input_path,"-vcodec",codec,"-crf",str(crf),"-preset",preset,"-acodec","aac","-b:a","96k","-progress","pipe:1",output_path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    start = asyncio.get_event_loop().time(); last_update = 0
    try:
        while True:
            line = await proc.stdout.readline()
            if not line: break
            s = line.decode(errors="ignore").strip(); now = asyncio.get_event_loop().time()
            if s.startswith("out_time_ms=") and dur_seconds>0:
                ms = int(s.split("=",1)[1]); sec = ms/1_000_000.0
                percent = min(100.0, (sec/dur_seconds)*100.0)
                elapsed = now - start; speed = (sec/elapsed) if elapsed>0 else 0.0
                rem = max(0.0, dur_seconds - sec); eta = int(rem / (speed if speed>0 else 1.0))
                if now - last_update >= 1.0:
                    try: await progress_message_obj.edit(ui_processing_block(percent=percent, speed=speed, eta=eta), parse_mode="html")
                    except: pass
                    last_update = now
        stderr = await proc.stderr.read(); await proc.wait()
        if proc.returncode == 0: return True, None, stderr.decode(errors="ignore")
        return False, f"ffmpeg exit {proc.returncode}", stderr.decode(errors="ignore")
    except Exception as e:
        try: await proc.kill()
        except: pass
        return False, str(e), ""

def format_dev_log(username, user_id, chat_id, infile, orig, out, profile, crf, ratio, meta, token=None):
    font = random.choice(FONTS); link_line = f"\nLOG LINK: https://t.me/{{bot}}?start=log_{token}" if token else ""
    return f"*** {font} DEV LOG ***\nUSER: @{username}\nUSER ID: {user_id}\nCHAT ID: {chat_id}\nINPUT: {infile}\nORIG: {orig}\nOUT: {out}\nRATIO: {ratio}\n{link_line}\nPROFILE: {profile}\nCRF: {crf}\nCODEC: {meta.get('codec')}\nRES: {meta.get('width')}x{meta.get('height')}\nFPS: {meta.get('fps')}\nTIME: {now_ts()}\n*** END ***"

def append_dev_log(record):
    arr = load_json(DEV_LOG_FILE, []); arr.append(record); arr = arr[-500:]; save_json(DEV_LOG_FILE, arr)

# worker routine
async def worker_routine(idx):
    while True:
        key = await queue.get()
        if key is None:
            queue.task_done(); break
        entry = pending.get(key)
        if not entry:
            queue.task_done(); continue
        try:
            chat_id = entry["chat_id"]; user = entry["from_user"]; msg_obj = entry["message_obj"]
            infile = entry["file"]; profile = entry.get("profile","turbo"); meta = entry.get("meta",{})
            dur = meta.get("duration",0.0); orig_size = os.path.getsize(infile) if os.path.exists(infile) else None
            prof_map = {"cinema":{"crf":22,"preset":"slow"},"turbo":{"crf":28,"preset":"fast"},"mobile":{"crf":30,"preset":"medium"},"archive":{"crf":32,"preset":"veryfast"}}
            prof = prof_map.get(profile, prof_map["turbo"]); crf = int(entry.get("crf", prof["crf"])); preset = entry.get("preset", prof["preset"])
            if entry.get("quality")=="high": crf = max(16, crf-4)
            if entry.get("quality")=="low": crf = min(40, crf+4)

            try: await msg_obj.reply(f"Starting compression — profile {profile}, estimated...")
            except: pass
            outfile = infile + "_compressed.mp4"; thumb = os.path.join(TMP, f"thumb_{os.path.basename(infile)}.jpg")
            try: await extract_thumbnail_safe(infile, thumb)
            except: pass
            try: progress_msg = await msg_obj.reply(ui_processing_block(0,0,0), parse_mode="html")
            except:
                try: progress_msg = await app.send_message(chat_id, ui_processing_block(0,0,0), parse_mode="html")
                except: progress_msg = None

            success, guidance, stderr_txt = await encode_with_progress(infile, outfile, crf, preset, progress_msg, dur, meta=meta)
            out_size = os.path.getsize(outfile) if os.path.exists(outfile) else None

            if success and out_size:
                ratio = (float(orig_size)/float(out_size)) if orig_size and out_size else None
                try:
                    await msg_obj.reply_document(document=open(outfile,"rb"), caption=ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"), force_document=True)
                except:
                    try: await app.send_document(chat_id, document=open(outfile,"rb"), caption=ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"))
                    except: pass

                token = make_token(12); lm = load_link_map(); lm[token] = {"ts": now_ts(), "user_id": user.get("id"), "username": user.get("username"), "chat_id": chat_id, "infile": os.path.basename(infile), "outfile": os.path.basename(outfile), "infile_path": infile, "outfile_path": outfile}; save_link_map(lm)
                cfg = load_admin_config(); log_channel = cfg.get("log_channel"); owners = cfg.get("owners", [])
                ratio_text = f"{ratio:.2f}×" if ratio else "N/A"
                log_msg = format_dev_log(user.get("username","unknown"), user.get("id"), chat_id, os.path.basename(infile), human_size(orig_size), human_size(out_size), profile, crf, ratio_text, {**meta, "chat_type": entry.get("chat_type","?")}, token=token)
                try:
                    bot_un = (await app.get_me()).username or ""
                    log_msg = log_msg.replace("{bot}", bot_un)
                except: pass
                try:
                    if log_channel: await app.send_message(log_channel, log_msg, parse_mode="html", disable_web_page_preview=True)
                except: pass
                for o in owners:
                    try: await app.send_message(o, log_msg, parse_mode="html", disable_web_page_preview=True)
                    except: pass

                append_history(user.get("id"), {"ts": now_ts(), "file": os.path.basename(infile), "orig": human_size(orig_size), "out": human_size(out_size), "profile": profile})
                append_dev_log({"ts": now_ts(), "user_id": user.get("id"), "username": user.get("username"), "chat_id": chat_id, "infile": os.path.basename(infile), "outfile": os.path.basename(outfile), "orig": human_size(orig_size), "out": human_size(out_size), "profile": profile, "token": token})

                try: os.remove(infile)
                except: pass
                try: os.remove(outfile)
                except: pass
                try: os.remove(thumb)
                except: pass
                try: await progress_msg.edit(ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"), parse_mode="html")
                except: pass

            else:
                try: await progress_msg.edit(f"Compression failed: {guidance}", parse_mode="html")
                except: pass
                try: await app.send_message(DEVELOPER_ID, f"Compression failed: {guidance}\nStderr excerpt:\n{(stderr_txt or '')[:1500]}")
                except: pass
                try: os.remove(infile)
                except: pass
                try: os.remove(outfile)
                except: pass

        except Exception as e:
            try: await app.send_message(DEVELOPER_ID, f"Worker exception: {str(e)[:300]}\n{traceback.format_exc()[:800]}")
            except: pass
        finally:
            try: pending.pop(key, None)
            except: pass
            try:
                if key in queue_deque: queue_deque.remove(key)
            except: pass
            queue.task_done()
            await asyncio.sleep(0.25)

# start workers
def start_worker_pool(loop):
    global worker_tasks
    if worker_tasks: return
    for i in range(WORKER_COUNT):
        t = loop.create_task(worker_routine(i)); worker_tasks.append(t)

async def stop_worker_pool():
    for _ in range(len(worker_tasks) or WORKER_COUNT):
        try: await queue.put(None)
        except: pass
    for t in worker_tasks:
        try:
            t.cancel(); await t
        except: pass

# Admin DM commands
@app.on_message(filters.private & filters.command("addowner"))
async def cmd_addowner(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    parts = m.text.split()
    if len(parts)<2: return await m.reply("Usage: /addowner <user_id>")
    try: uid = int(parts[1])
    except: return await m.reply("Invalid user id.")
    cfg = load_admin_config(); owners = cfg.get("owners", [])
    if uid in owners: return await m.reply("User already an owner.")
    owners.append(uid); cfg["owners"]=owners; save_admin_config(cfg); return await m.reply(f"Added owner: {uid}")

@app.on_message(filters.private & filters.command("removeowner"))
async def cmd_removeowner(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    parts = m.text.split(); 
    if len(parts)<2: return await m.reply("Usage: /removeowner <user_id>")
    try: uid = int(parts[1])
    except: return await m.reply("Invalid user id.")
    cfg = load_admin_config(); owners = cfg.get("owners", [])
    if uid not in owners: return await m.reply("User not an owner.")
    owners.remove(uid); cfg["owners"]=owners; save_admin_config(cfg); return await m.reply(f"Removed owner: {uid}")

@app.on_message(filters.private & filters.command("listowners"))
async def cmd_listowners(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    cfg = load_admin_config(); owners = cfg.get("owners", [])
    await m.reply("Owners:\n" + "\n".join([str(x) for x in owners]))

@app.on_message(filters.private & filters.command("setlogchannel"))
async def cmd_setlogchannel(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    parts = m.text.split()
    if len(parts)<2: return await m.reply("Usage: /setlogchannel <channel_id>")
    try: cid = int(parts[1])
    except: return await m.reply("Invalid channel id.")
    cfg = load_admin_config(); cfg["log_channel"]=cid; save_admin_config(cfg); await m.reply(f"Log channel set to {cid}")

@app.on_message(filters.private & filters.command("getconfig"))
async def cmd_getconfig(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    cfg = load_admin_config(); await m.reply("Config:\n" + json.dumps(cfg, indent=2))

@app.on_message(filters.private & filters.command("devlogs"))
async def cmd_devlogs(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    arr = load_json(DEV_LOG_FILE, []); txt = "Recent logs:\n" + "\n".join([f"{i+1}. {x.get('ts')} - {x.get('username')} - {x.get('infile')}" for i,x in enumerate(arr[-20:])]); await m.reply(txt)

@app.on_message(filters.private & filters.command("links"))
async def cmd_links(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    lm = load_link_map(); txt = "Active Links:\n" + "\n".join([f"{k} -> {v.get('outfile') or v.get('infile')} (user:{v.get('username')})" for k,v in list(lm.items())[-50:]])
    await m.reply(txt)

# Broadcast command (DM only): /broadcast <all|dm> <text>
@app.on_message(filters.private & filters.command("broadcast"))
async def cmd_broadcast(_, m):
    if not is_owner(m.from_user.id): return await m.reply("⛔ You are not an owner.")
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3 and not m.reply_to_message: return await m.reply("Usage: /broadcast all|dm <text> (or reply to media)")
    mode = parts[1].lower() if len(parts)>=2 else "all"; payload = parts[2] if len(parts)>=3 else ""
    history = load_json(HISTORY_FILE, {}); targets = []
    if mode=="all": targets = [int(uid) for uid in history.keys() if history.get(uid)]
    elif mode=="dm":
        for uid,lst in history.items():
            if lst and lst[-1].get("chat_type")=="Private": targets.append(int(uid))
    else: return await m.reply("Unknown mode. Use all or dm.")
    await m.reply(f"Broadcasting to {len(targets)} users...")
    sent=0; failed=0
    if m.reply_to_message:
        for uid in targets:
            try: await app.copy_message(int(uid), m.chat.id, m.reply_to_message.message_id); sent+=1
            except: failed+=1
    else:
        for uid in targets:
            try: await app.send_message(int(uid), payload); sent+=1
            except: failed+=1
    await m.reply(f"Broadcast finished. Sent: {sent} Failed: {failed}")

# dashboard (optional)
if DASH_AVAILABLE:
    async def dashboard_index(request):
        q_items = list(queue_deque); pending_count = len(pending)
        html = "<html><head><title>Neon Titanium</title></head><body style='background:#071028;color:#fff;padding:20px;font-family:Arial'>"
        html += f"<h1>Neon Titanium</h1><div>Queue size: {len(q_items)} Pending: {pending_count}</div><div><ol>"
        for k in q_items[:200]:
            e = pending.get(k,{}); user = e.get("from_user",{})
            html += f"<li>{k} — @{user.get('username','unknown')} — {e.get('chat_type','?')}</li>"
        html += "</ol></div></body></html>"; return web.Response(text=html, content_type='text/html')
    def start_dashboard_app(port=8080):
        app_dash = web.Application(); app_dash.router.add_get("/", dashboard_index); runner = web.AppRunner(app_dash)
        async def _run():
            await runner.setup(); site = web.TCPSite(runner, '0.0.0.0', port); await site.start()
        asyncio.create_task(_run()); return runner
else:
    def start_dashboard_app(port=8080): return None

# start/stop
@app.on_message(filters.user(DEVELOPER_ID) & filters.command("stats"))
async def cmd_stats(_, m):
    qlen = queue.qsize(); pend = len(pending)
    try: disk = shutil.disk_usage(TMP); used = human_size(disk.used); total = human_size(disk.total)
    except: used="Unknown"; total="Unknown"
    await m.reply(f"Titanium Status\nQueue size: {qlen}\nPending: {pend}\nTemp used: {used} / {total}")

@app.on_message(filters.user(DEVELOPER_ID) & filters.command("reset_queue"))
async def cmd_reset(_, m):
    try:
        while not queue.empty():
            try: k = queue.get_nowait(); queue.task_done()
            except: break
        for k in list(pending.keys()): e = pending.pop(k, None)
        await m.reply("Queue and pending cleared.")
    except Exception as e: await m.reply(f"Error clearing queue: {str(e)}")

async def _main():
    print("Neon Titanium — starting...")
    try: await app.start()
    except Exception as e: print("Failed to start pyrogram client:", e); return
    me = await app.get_me(); print(f"Bot username: @{me.username}")
    if DASH_AVAILABLE: start_dashboard_app(port=8080); print("Dashboard running on port 8080")
    start_worker_pool(asyncio.get_running_loop()); print(f"Worker pool online → {WORKER_COUNT} workers active")
    try: await asyncio.Event().wait()
    finally:
        await stop_worker_pool()
        try: await app.stop()
        except: pass

def run():
    asyncio.run(_main())

if __name__ == "__main__":
    run()

    except (KeyboardInterrupt, SystemExit): print("Shutting down...")
    except Exception as e: print("Fatal error in main:", e)
