import io

import requests


def download_thumbnail_bytes(video_id):
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
                print(f"  Thumbnail Ram'e indirildi: {quality}.jpg ({len(data) / 1024:.0f} KB)")
                return data
        except Exception:
            continue

    print(f"  UYARI: Thumbnail indirilemedi ({video_id})")
    return None


def bytesio(data):
    buf = io.BytesIO(data)
    buf.seek(0)
    return buf