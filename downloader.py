import os, uuid, subprocess, requests
from config import TMP_DIR, USE_EXTERNAL_API, DOWNLOADER_API_URL, API_KEY

def download_from_link(url):
    out = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")

    if USE_EXTERNAL_API and DOWNLOADER_API_URL:
        r = requests.post(
            DOWNLOADER_API_URL,
            json={"url": url, "key": API_KEY},
            timeout=120
        )
        with open(out, "wb") as f:
            f.write(r.content)
        return out

    subprocess.run(
        ["yt-dlp", "-f", "mp4/best", "-o", out, url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if not os.path.exists(out):
        raise RuntimeError("Download failed")

    return out
