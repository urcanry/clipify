import os
import re

import requests

from config import KAPAK_DIR


def sanitize_filename(title):
    t = re.sub(r'[\\/:*?"<>|]+', " ", title or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.rstrip(". ")
    if len(t) > 80:
        t = t[:80].rstrip()
    return t or "video"


def download_original_thumbnail(video_id, title):
    qualities = [
        "maxresdefault",
        "sddefault",
        "hqdefault",
        "mqdefault",
    ]

    for quality in qualities:
        url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
                data = resp.content
                os.makedirs(KAPAK_DIR, exist_ok=True)
                name = sanitize_filename(title)
                path = os.path.join(KAPAK_DIR, f"{name}.jpg")
                with open(path, "wb") as f:
                    f.write(data)
                print(f"  Orijinal kapak indirildi: {path} ({len(data) / 1024:.0f} KB)")
                return path
        except Exception:
            continue

    print(f"  UYARI: Orijinal kapak indirilemedi ({video_id})")
    return None