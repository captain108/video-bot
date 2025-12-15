import os, time

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = int(os.getenv("DEVELOPER_ID"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))

BOT_USERNAME = "captainpapaji_bot"

TMP_DIR = "/tmp/neon_cloud"
os.makedirs(TMP_DIR, exist_ok=True)

# link expiry (seconds)
LINK_EXPIRY = 6 * 60 * 60

# ===== FUTURE API PLACEHOLDERS =====
USE_EXTERNAL_API = False
DOWNLOADER_API_URL = os.getenv("DOWNLOADER_API_URL", "")
COMPRESSOR_API_URL = os.getenv("COMPRESSOR_API_URL", "")
API_KEY = os.getenv("EXTERNAL_API_KEY", "")
