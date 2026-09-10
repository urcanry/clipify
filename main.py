"""
YouTube Automator (Clipify) - Ana Orkestrator
- Kanal takibi (RSS)
- Sadece uzun videolari secer (Shorts haric)
- Video RAM'e indirilir, islenir, YouTube'a taslak olarak yuklenir
- GitHub Actions cron modu: python main.py --run-once
"""

import os
import sys
import time
import asyncio
import argparse
import threading
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import (
    CHANNELS, OUTPUT_DIR, THUMBNAIL_DIR, INTRO_FILE,
    MONITOR_INTERVAL, MIN_VIDEO_DURATION, MAX_VIDEO_DURATION,
    AUTO_UPLOAD, YOUTUBE_PRIVACY,
)

from monitor import check_all_channels, load_processed, save_processed
from downloader import download_to_memory, get_video_info
from intro_detector import detect_intro_end
from render import render_final, generate_preview
from thumbnail import download_thumbnail_bytes
from telegram_bot import (
    notify_new_video, send_preview, send_uploaded_message,
    load_pending, save_pending, handle_approve_sync,
)
from uploader import upload_clip


def setup_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def is_long_video(info):
    duration = info.get("duration", 0)
    if duration < MIN_VIDEO_DURATION:
        print(f"  ATLANDI: {duration // 60}:{duration % 60:02d} - Shorts/kisa video (min {MIN_VIDEO_DURATION}s)")
        return False
    if duration > MAX_VIDEO_DURATION:
        print(f"  ATLANDI: {duration // 60}:{duration % 60:02d} - cok uzun (max {MAX_VIDEO_DURATION}s)")
        return False
    return True


def process_video(url, channel_name="Bilinmeyen"):
    print(f"\n{'='*60}")
    print(f"VIDEO ISLENIYOR")
    print(f"URL: {url}")
    print(f"Kanal: {channel_name}")
    print(f"Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    info = get_video_info(url)
    if not info:
        print("HATA: Video bilgisi alinamadi")
        return None

    video_id = info.get("id", "")
    title = info.get("title", "")
    duration = info.get("duration", 0)
    description = info.get("description", "")

    print(f"  Baslik: {title}")
    print(f"  Sure: {duration // 60}:{duration % 60:02d}")

    if not is_long_video(info):
        return {"skipped": "short_or_long", "video_id": video_id, "title": title}

    if not os.path.exists(INTRO_FILE):
        print("HATA: 'YouTube Intro.mp4' bulunamadi. Proje dizinine ekleyin.")
        print(f"Aranan yol: {INTRO_FILE}")
        return None

    print(f"\n[1/5] Video RAM'e indiriliyor (disk kullanilmadan)...")
    video_stream = download_to_memory(url)
    if video_stream is None:
        return None
    video_bytes = video_stream.getvalue()

    print(f"\n[2/5] Intro tespiti yapiliyor...")
    intro_end = detect_intro_end(video_id, video_bytes, duration)
    print(f"  Intro bitis: {intro_end:.1f}s")

    print(f"\n[3/5] Intro birlesitirilip video isleniyor (RAM)...")
    final_bytes = render_final(
        video_bytes,
        intro_end,
        fallback_size=(info.get("width") or 1920, info.get("height") or 1080),
    )
    if final_bytes is None:
        print("HATA: Video islenemedi")
        return None
    del video_bytes
    del video_stream

    print(f"\n[4/5] Thumbnail RAM'e indiriliyor...")
    thumbnail_bytes = download_thumbnail_bytes(video_id)

    clip_info = {
        "video_id": video_id,
        "title": title,
        "channel": channel_name,
        "original_url": url,
        "intro_end": intro_end,
        "description": description,
        "status": "pending",
    }

    if AUTO_UPLOAD:
        print(f"\n[5/5] YouTube'a yukleniyor (AUTO_UPLOAD acik, taslak: {YOUTUBE_PRIVACY})...")
        vid, youtube_url = upload_clip(
            mp4_bytes=final_bytes,
            info=clip_info,
            thumbnail_bytes=thumbnail_bytes,
        )
        if vid:
            clip_info["status"] = "uploaded"
            clip_info["youtube_url"] = youtube_url
            print(f"\n{'='*60}")
            print(f"YUKLENDI (taslak): {youtube_url}")
            print(f"{'='*60}")
            asyncio.run(send_uploaded_message(clip_info))
            return clip_info
        print("Yukleme basarisiz")
        return None

    print(f"\n[5/5] Onay icin kaydediliyor ve Telegram'a gonderiliyor...")
    clip_id = f"{video_id}_{int(time.time())}"
    video_path = os.path.join(OUTPUT_DIR, f"{video_id}_final.mp4")
    thumb_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")

    with open(video_path, "wb") as f:
        f.write(final_bytes)
    if thumbnail_bytes:
        with open(thumb_path, "wb") as f:
            f.write(thumbnail_bytes)

    clip_info["clip_id"] = clip_id
    clip_info["video_path"] = video_path
    clip_info["thumbnail_path"] = thumb_path
    load_pending()
    from telegram_bot import pending_clips
    pending_clips[clip_id] = clip_info
    save_pending()

    preview_bytes = generate_preview(final_bytes)
    if preview_bytes:
        asyncio.run(send_preview(clip_id, preview_bytes, clip_info))

    print(f"\n{'='*60}")
    print(f"ISLEME TAMAMLANDI")
    print(f"  Clip ID: {clip_id}")
    print(f"  Intro kesildi: {intro_end:.0f}s")
    print(f"  Onay: Telegram'dan 'Onayla' butonu")
    print(f"{'='*60}")
    return clip_info


def mark_processed(video_id, status, extra=None):
    processed = load_processed()
    entry = processed.get(video_id, {})
    entry["status"] = status
    entry["processed_at"] = datetime.now().isoformat()
    if extra:
        entry.update(extra)
    processed[video_id] = entry
    save_processed(processed)


def run_once_mode():
    print(f"{'='*60}")
    print(f"RUN-ONCE MODU (GitHub Actions cron icin)")
    print(f"Kanallar: {', '.join(CHANNELS.keys())}")
    print(f"AUTO_UPLOAD: {AUTO_UPLOAD}")
    print(f"{'='*60}\n")

    new_videos = check_all_channels()

    if not new_videos:
        print("\nYeni video bulunamadi. Bitti.")
        return

    for item in new_videos:
        video = item["video"]
        channel_name = item["channel_name"]
        url = video["url"]

        try:
            result = process_video(url, channel_name)
            if result is None:
                mark_processed(video["video_id"], "failed")
            elif result.get("skipped"):
                mark_processed(video["video_id"], "skipped_short")
            elif result.get("status") == "uploaded":
                mark_processed(video["video_id"], "uploaded", {"youtube_url": result.get("youtube_url", "")})
            else:
                mark_processed(video["video_id"], "pending_approval")
        except Exception as e:
            print(f"HATA: {e}")
            mark_processed(video["video_id"], "failed")

    print("\nRUN-ONCE TAMAMLANDI")


def monitor_mode():
    print(f"{'='*60}")
    print(f"MONITOR MODU BASLATILDI")
    print(f"Kontrol araligi: {MONITOR_INTERVAL} saniye")
    print(f"Takip edilen kanallar: {', '.join(CHANNELS.keys())}")
    print(f"AUTO_UPLOAD: {AUTO_UPLOAD}")
    print(f"{'='*60}\n")

    setup_dirs()

    def run_telegram_bot():
        from telegram_bot import build_app
        app = build_app()
        app.run_polling(allowed_updates=["callback_query", "message"])

    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    print("Telegram bot baslatildi\n")

    while True:
        try:
            new_videos = check_all_channels()

            for item in new_videos:
                video = item["video"]
                channel_name = item["channel_name"]
                url = video["url"]

                asyncio.run(notify_new_video(
                    channel_name=channel_name,
                    title=video["title"],
                    url=url,
                    thumbnail_url=video.get("thumbnail", ""),
                ))

                print(f"\nYeni video isleniyor: {channel_name} - {video['title'][:50]}...")
                result = process_video(url, channel_name)
                if result is None:
                    mark_processed(video["video_id"], "failed")
                elif result.get("skipped"):
                    mark_processed(video["video_id"], "skipped_short")
                elif result.get("status") == "uploaded":
                    mark_processed(video["video_id"], "uploaded", {"youtube_url": result.get("youtube_url", "")})
                else:
                    mark_processed(video["video_id"], "pending_approval")

        except KeyboardInterrupt:
            print("\nMonitor durduruldu.")
            break
        except Exception as e:
            print(f"HATA: {e}")

        print(f"\nSonraki kontrol: {MONITOR_INTERVAL} saniye sonra...")
        time.sleep(MONITOR_INTERVAL)


def check_mode():
    print(f"{'='*60}")
    print(f"KONTROL MODU (sadece goruntuleme, isleme yok)")
    print(f"{'='*60}\n")
    new_videos = check_all_channels()
    if not new_videos:
        print("\nYeni video bulunamadi.")
        return
    for item in new_videos:
        video = item["video"]
        print(f"\n  [{item['channel_name']}] {video['title']}")
        print(f"  URL: {video['url']}")


def process_mode(url):
    process_video(url)


def approve_mode(clip_id):
    load_pending()
    result = handle_approve_sync(clip_id)
    if not result:
        print(f"Clip bulunamadi: {clip_id}")
        return

    video_path = result.get("video_path")
    if not video_path or not os.path.exists(video_path):
        print("HATA: Video dosyasi bulunamadi")
        return

    with open(video_path, "rb") as f:
        mp4_bytes = f.read()

    thumb_bytes = None
    thumb_path = result.get("thumbnail_path")
    if thumb_path and os.path.exists(thumb_path):
        with open(thumb_path, "rb") as t:
            thumb_bytes = t.read()

    video_id, youtube_url = upload_clip(
        mp4_bytes=mp4_bytes,
        info=result,
        thumbnail_bytes=thumb_bytes,
    )

    if video_id:
        print(f"YouTube'a taslak olarak yuklendi: {youtube_url}")
    else:
        print("Yukleme basarisiz")


def reject_mode(clip_id):
    load_pending()
    from telegram_bot import handle_reject_sync
    result = handle_reject_sync(clip_id)
    if result:
        print(f"Clip reddedildi ve silindi: {clip_id}")
    else:
        print(f"Clip bulunamadi: {clip_id}")


def main():
    parser = argparse.ArgumentParser(description="YouTube Automator (Clipify)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--monitor", action="store_true", help="Surekli takip + Telegram onay akisi")
    group.add_argument("--run-once", action="store_true", help="GitHub Actions cron: tek seferlik kontrol + isleme")
    group.add_argument("--check", action="store_true", help="Yeni videolari goruntule")
    group.add_argument("--url", type=str, help="Tek video isle")
    group.add_argument("--approve", type=str, help="Clip onayla (clip_id)")
    group.add_argument("--reject", type=str, help="Clip red et (clip_id)")

    args = parser.parse_args()

    setup_dirs()

    if args.monitor:
        monitor_mode()
    elif args.run_once:
        run_once_mode()
    elif args.check:
        check_mode()
    elif args.url:
        process_mode(args.url)
    elif args.approve:
        approve_mode(args.approve)
    elif args.reject:
        reject_mode(args.reject)


if __name__ == "__main__":
    main()