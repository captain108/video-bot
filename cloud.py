import random, string, time, re
from config import LOG_CHANNEL, BOT_USERNAME, LINK_EXPIRY

cloud_db = {}
TOKEN_RE = re.compile(r"NEON_TOKEN:\s*(\w+)")

def make_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

def caption(token, user_id):
    return (
        "☁️ NEON CLOUD STORAGE\n"
        f"NEON_TOKEN: {token}\n"
        f"USER_ID: {user_id}\n"
        f"TIME: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

async def store_file(bot, file_path, user_id):
    token = make_token()
    msg = await bot.send_document(
        LOG_CHANNEL,
        file_path,
        caption=caption(token, user_id)
    )
    cloud_db[token] = {
        "chat_id": LOG_CHANNEL,
        "message_id": msg.id,
        "ts": time.time()
    }
    return token

async def fetch_file(bot, token, user_id):
    data = cloud_db.get(token)
    if not data:
        return False
    if time.time() - data["ts"] > LINK_EXPIRY:
        cloud_db.pop(token, None)
        return False
    await bot.copy_message(
        user_id,
        data["chat_id"],
        data["message_id"]
    )
    return True

def make_link(token):
    return f"https://t.me/{BOT_USERNAME}?start=cloud_{token}"
