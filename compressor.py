import subprocess, os, requests
from config import USE_EXTERNAL_API, COMPRESSOR_API_URL, API_KEY

def compress_video(inp, out):
    if USE_EXTERNAL_API and COMPRESSOR_API_URL:
        with open(inp, "rb") as f:
            r = requests.post(
                COMPRESSOR_API_URL,
                files={"file": f},
                data={"key": API_KEY}
            )
        with open(out, "wb") as o:
            o.write(r.content)
        return os.path.exists(out)

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", inp,
            "-vcodec", "libx264", "-crf", "28",
            "-preset", "fast",
            "-acodec", "aac", "-b:a", "96k",
            out
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return os.path.exists(out)
