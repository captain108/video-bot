import os, subprocess, threading, time
from flask import Flask

app = Flask(__name__)
process = None

def start_bot():
    global process
    if not process or process.poll() is not None:
        process = subprocess.Popen(["python3", "app.py"])

def monitor():
    while True:
        start_bot()
        time.sleep(300)

@app.route("/")
def health():
    return "Neon Cloud Bot Running"

if __name__ == "__main__":
    start_bot()
    threading.Thread(target=monitor, daemon=True).start()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        use_reloader=False
    )
