from pyrogram import Client, filters
from config import *
from cloud import *
from downloader import *
from compressor import *
import os

bot = Client(
    "neon-cloud-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

users = set()

@bot.on_message(filters.private)
async def track(_, m):
    users.add(m.from_user.id)

@bot.on_message(filters.command("start"))
async def start(_, m):
    users.add(m.from_user.id)

    if m.text.startswith("/start cloud_"):
        token = m.text.split("_", 1)[1]
        ok = await fetch_file(bot, token, m.from_user.id)
        if not ok:
            await m.reply("❌ Link expired or invalid.")
        return

    await m.reply(
        "☁️ Neon Cloud Bot\n\n"
        "📤 Send media\n"
        "🌐 Send link\n"
        "🎞 Auto compress\n\n"
        "Owner: @captainpapaji"
    )

@bot.on_message(filters.video | filters.document)
async def media(_, m):
    users.add(m.from_user.id)
    path = await m.download(file_name=TMP_DIR)
    out = f"{path}_c.mp4"

    compress_video(path, out)
    token = await store_file(bot, out, m.from_user.id)

    await m.reply(f"✅ Stored\n🔗 {make_link(token)}")
    os.remove(path); os.remove(out)

@bot.on_message(filters.text & filters.private)
async def links(_, m):
    if not m.text.startswith("http"):
        return

    path = download_from_link(m.text)
    out = f"{path}_c.mp4"

    compress_video(path, out)
    token = await store_file(bot, out, m.from_user.id)

    await m.reply(f"☁️ Stored\n🔗 {make_link(token)}")
    os.remove(path); os.remove(out)

# ===== BROADCAST =====
@bot.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(_, m):
    if not m.reply_to_message:
        await m.reply("Reply to a message to broadcast.")
        return

    sent = 0
    for uid in list(users):
        try:
            await m.reply_to_message.copy(uid)
            sent += 1
        except:
            pass

    await m.reply(f"Broadcast sent to {sent} users.")

def run():
    bot.run()

if __name__ == "__main__":
    run()
