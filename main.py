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
    CHANNELS, OUTPUT_DIR, KAPAK_DIR, INTRO_FILE,
    MONITOR_INTERVAL, MIN_VIDEO_DURATION, MAX_VIDEO_DURATION,
    AUTO_UPLOAD, YOUTUBE_PRIVACY, DUPLICATE_CHECK,
)

from monitor import check_all_channels, load_processed, save_processed
from fingerprint import compute_fingerprint, find_duplicate
from downloader import download_to_memory, get_video_info
from intro_detector import detect_intro_end
from render import render_final, generate_gif
from ffmpeg_utils import probe_duration_file
from thumbnail import download_original_thumbnail
from telegram_bot import notify_new_video, send_uploaded_message
from uploader import upload_clip


def setup_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(KAPAK_DIR, exist_ok=True)


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

    if DUPLICATE_CHECK:
        full_fp = compute_fingerprint(title, duration)
        existing = load_processed()
        dup_vid = find_duplicate(full_fp, existing)
        if dup_vid and dup_vid != video_id:
            dup_title = existing[dup_vid].get("title", "?")
            print(f"  MUKERRER VIDEO: Ayni icerik daha once yuklendi")
            print(f"    Onceki: [{dup_vid}] {dup_title[:50]}")
            print(f"    Fingerprint: {full_fp}")
            return {"skipped": "duplicate", "video_id": video_id, "title": title,
                    "duplicate_of": dup_vid, "fingerprint": full_fp}
        existing[video_id] = existing.get(video_id, {})
        existing[video_id]["fingerprint"] = full_fp
        save_processed(existing)

    if not is_long_video(info):
        return {"skipped": "short_or_long", "video_id": video_id, "title": title}

    if not os.path.exists(INTRO_FILE):
        print("HATA: 'YouTube Intro.mp4' bulunamadi. Proje dizinine ekleyin.")
        print(f"Aranan yol: {INTRO_FILE}")
        return None

    print(f"\n[1/4] Video RAM'e indiriliyor (disk kullanilmadan)...")
    video_stream = download_to_memory(url)
    if video_stream is None:
        return None
    video_bytes = video_stream.getvalue()

    print(f"\n[2/4] Intro tespiti yapiliyor...")
    intro_end = detect_intro_end(video_id, video_bytes, duration)
    print(f"  Intro bitis: {intro_end:.1f}s")

    print(f"\n[3/4] Intro birlesitirilip video isleniyor (RAM)...")
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

    print(f"\n[4/5] Orijinal kapak indirilip 'Kapaklar' klasorune kaydediliyor...")
    thumbnail_path = download_original_thumbnail(video_id, title)

    clip_info = {
        "video_id": video_id,
        "title": title,
        "original_title": title,
        "channel": channel_name,
        "original_url": url,
        "intro_end": intro_end,
        "description": description,
        "thumbnail_path": thumbnail_path,
        "status": "uploading",
    }

    print(f"\n[5/5] YouTube'a yukleniyor (otonom, taslak: {YOUTUBE_PRIVACY})...")
    print(f"  Baslik (orijinal): {title}")
    vid, youtube_url = upload_clip(
        mp4_bytes=final_bytes,
        info=clip_info,
    )
    if vid:
        clip_info["status"] = "uploaded"
        clip_info["youtube_url"] = youtube_url
        clip_info["youtube_video_id"] = vid
        clip_info["privacy"] = YOUTUBE_PRIVACY

        print(f"\n{'='*60}")
        print(f"YUKLENDI (taslak): {youtube_url}")
        print(f"{'='*60}")

        try:
            intro_dur = probe_duration_file(INTRO_FILE) or 0
            final_duration = max((duration - intro_end) + intro_dur, 10)
            print("\nOnizleme GIF'leri olusturuluyor...")
            first_gif = generate_gif(final_bytes, 0, 10)
            last_gif = generate_gif(final_bytes, final_duration - 10, 10)
            print("Telegram bildirimi gonderiliyor...")
            asyncio.run(send_uploaded_message(
                clip_info,
                first_gif=first_gif,
                last_gif=last_gif,
                original_description=description,
            ))
        except Exception as e:
            print(f"UYARI: Bildirim gonderilemedi: {e}")

        return clip_info

    print("HATA: Yukleme basarisiz")
    return None


def mark_processed(video_id, status, extra=None):
    processed = load_processed()
    entry = processed.get(video_id, {})
    entry["status"] = status
    entry["processed_at"] = datetime.now().isoformat()
    if extra:
        entry.update(extra)
    processed[video_id] = entry
    save_processed(processed)
    return entry


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
            elif result.get("skipped") == "duplicate":
                mark_processed(video["video_id"], "duplicate_skipped", {
                    "fingerprint": result.get("fingerprint", ""),
                    "duplicate_of": result.get("duplicate_of", ""),
                })
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
                elif result.get("skipped") == "duplicate":
                    mark_processed(video["video_id"], "duplicate_skipped", {
                        "fingerprint": result.get("fingerprint", ""),
                        "duplicate_of": result.get("duplicate_of", ""),
                    })
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
    result = process_video(url)
    if result is None:
        mark_processed("", "failed")
    elif result.get("skipped"):
        mark_processed(result.get("video_id", ""), "skipped_short")
    elif result.get("status") == "uploaded":
        mark_processed(result.get("video_id", ""), "uploaded", {
            "youtube_url": result.get("youtube_url", ""),
        })


def approve_mode(clip_id):
    print("UYARI: Onay akisi kaldirildi. Yükleme artik otonom yapilir.")


def reject_mode(clip_id):
    print("UYARI: Onay akisi kaldirildi. Yükleme artik otonom yapilir.")


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