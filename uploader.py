import os
import sys
import io
import json
from datetime import datetime

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

from config import (
    YOUTUBE_PRIVACY,
    YOUTUBE_CATEGORY,
    YOUTUBE_TAGS,
    UPLOADS_FILE,
)
from title_generator import generate_description, generate_tags

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")


def get_credentials():
    if not os.path.exists(TOKEN_FILE):
        print("HATA: token.json bulunamadi!")
        print("Once: python setup_auth.py")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())
    return creds


def get_youtube_service():
    creds = get_credentials()
    return build("youtube", "v3", credentials=creds)


def load_uploaded():
    if os.path.exists(UPLOADS_FILE):
        with open(UPLOADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_uploaded(uploaded):
    os.makedirs(os.path.dirname(UPLOADS_FILE), exist_ok=True)
    with open(UPLOADS_FILE, "w", encoding="utf-8") as f:
        json.dump(uploaded, f, indent=2, ensure_ascii=False)


def set_thumbnail(video_id, thumbnail_bytes):
    if not thumbnail_bytes:
        return False

    youtube = get_youtube_service()
    try:
        media = MediaIoBaseUpload(
            io.BytesIO(thumbnail_bytes),
            mimetype="image/jpeg",
        )
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
        print(f"  Thumbnail eklendi: {video_id}")
        return True
    except HttpError as e:
        print(f"  UYARI: Thumbnail eklenemedi: {e}")
        return False


def update_video_title(video_id, new_title):
    youtube = get_youtube_service()
    try:
        current = youtube.videos().list(part="snippet", id=video_id).execute()
        if not current.get("items"):
            print(f"  HATA: Video bulunamadi: {video_id}")
            return False
        snippet = current["items"][0]["snippet"]
        snippet["title"] = new_title[:100]
        youtube.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": snippet},
        ).execute()
        print(f"  Baslik guncellendi: {new_title[:50]}...")
        return True
    except HttpError as e:
        print(f"  UYARI: Baslik guncellenemedi: {e}")
        return False


def set_privacy(video_id, privacy):
    youtube = get_youtube_service()
    try:
        current = youtube.videos().list(part="status", id=video_id).execute()
        if not current.get("items"):
            print(f"  HATA: Video bulunamadi: {video_id}")
            return False
        status = current["items"][0]["status"]
        status["privacyStatus"] = privacy
        youtube.videos().update(
            part="status",
            body={"id": video_id, "status": status},
        ).execute()
        print(f"  Gizlilik guncellendi: {privacy}")
        return True
    except HttpError as e:
        print(f"  UYARI: Gizlilik guncellenemedi: {e}")
        return False


def publish_video(video_id):
    return set_privacy(video_id, "public")


def upload_video(mp4_bytes, title, description, tags=None, thumbnail_bytes=None,
                 privacy=YOUTUBE_PRIVACY, category=YOUTUBE_CATEGORY):
    youtube = get_youtube_service()

    if tags is None:
        tags = YOUTUBE_TAGS

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaIoBaseUpload(
        io.BytesIO(mp4_bytes),
        mimetype="video/mp4",
        chunksize=1024 * 1024,
        resumable=True,
    )
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    print(f"  Yukleniyor: {len(mp4_bytes) / (1024 * 1024):.1f} MB (mod: {privacy})")
    response = None

    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            print(f"  Upload: %{progress}", end="\r")

    video_id = response.get("id")
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"\n  BASARILI: {url}")

        if thumbnail_bytes:
            set_thumbnail(video_id, thumbnail_bytes)

        return video_id, url

    print("\n  HATA: Video ID alinamadi")
    return None, None


def upload_clip(mp4_bytes, info, thumbnail_bytes=None, tags=None):
    video_id = info.get("video_id", "")
    original_title = info.get("title", "")
    original_url = info.get("original_url", "")
    channel_name = info.get("channel", "")
    intro_end = info.get("intro_end", 0)

    title = original_title
    description = generate_description(
        video_id, original_title, channel_name, intro_end, original_url
    )
    if tags is None:
        tags = generate_tags(original_title, channel_name)

    print(f"\n  Yuklenen baslik (orijinal): {title}")

    vid, url = upload_video(
        mp4_bytes=mp4_bytes,
        title=title,
        description=description,
        tags=tags,
        thumbnail_bytes=thumbnail_bytes,
        privacy=YOUTUBE_PRIVACY,
    )

    if vid:
        uploaded = load_uploaded()
        uploaded[vid] = {
            "title": title,
            "original_url": original_url,
            "channel": channel_name,
            "uploaded_at": datetime.now().isoformat(),
            "privacy": YOUTUBE_PRIVACY,
            "youtube_url": url,
        }
        save_uploaded(uploaded)

    return vid, url