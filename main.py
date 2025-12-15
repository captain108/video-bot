import os
import subprocess
import time
import threading
import signal
from flask import Flask, jsonify

app = Flask(__name__)

APP_SCRIPT = "app.py"
CHECK_INTERVAL = 300  # 5 minutes
process = None
lock = threading.Lock()

def start_bot():
    global process
    with lock:
        if process and process.poll() is None:
            return

        print("🚀 Starting Telegram bot...")
        process = subprocess.Popen(
            ["python3", APP_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )

def is_running():
    return process is not None and process.poll() is None

def monitor():
    while True:
        with lock:
            if not is_running():
                print("❌ Bot stopped. Restarting...")
                start_bot()
            else:
                print("✅ Bot running")
        time.sleep(CHECK_INTERVAL)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "bot": "running" if is_running() else "stopped",
        "service": "neon-titanium"
    })

def shutdown(*_):
    global process
    print("🛑 Shutting down supervisor...")
    if process and process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    os._exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    start_bot()

    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
