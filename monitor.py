import os
import sys
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import CHANNELS, PROCESSED_FILE, DUPLICATE_CHECK
from fingerprint import compute_fingerprint, find_duplicate

RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NS = "http://search.yahoo.com/mrss/"


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_processed(processed):
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)


def fetch_rss(channel_id):
    url = RSS_URL.format(channel_id=channel_id)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")
    except URLError as e:
        print(f"  HATA: RSS alinamadi ({channel_id}): {e}")
        return None


def parse_rss(xml_content):
    videos = []
    try:
        root = ET.fromstring(xml_content)
        for entry in root.findall(f"{{{ATOM_NS}}}entry"):
            video_id_el = entry.find(f"{{{YT_NS}}}videoId")
            if video_id_el is None:
                continue
            video_id = video_id_el.text
            title_el = entry.find(f"{{{ATOM_NS}}}title")
            title = title_el.text if title_el is not None else ""
            published_el = entry.find(f"{{{ATOM_NS}}}published")
            published = published_el.text if published_el is not None else ""
            link_el = entry.find(f"{{{ATOM_NS}}}link")
            link = link_el.attrib.get("href", "") if link_el is not None else ""
            desc_el = entry.find(f"{{{MEDIA_NS}}}group/{{{MEDIA_NS}}}description")
            description = desc_el.text if desc_el is not None and desc_el.text else ""
            thumb_el = entry.find(f"{{{MEDIA_NS}}}group/{{{MEDIA_NS}}}thumbnail")
            thumbnail = thumb_el.attrib.get("url", "") if thumb_el is not None else ""

            videos.append({
                "video_id": video_id,
                "title": title,
                "published": published,
                "url": link,
                "description": description,
                "thumbnail": thumbnail,
            })
    except ET.ParseError as e:
        print(f"  HATA: XML ayristirma hatasi: {e}")
    return videos


def check_channel(channel_key):
    channel_info = CHANNELS[channel_key]
    print(f"[{channel_info['name']}] Kontrol ediliyor...")

    xml = fetch_rss(channel_info["id"])
    if not xml:
        return []

    videos = parse_rss(xml)
    if not videos:
        print(f"  Video bulunamadi")
        return []

    processed = load_processed()
    first_run = not os.path.exists(PROCESSED_FILE) and not any(processed)
    new_videos = []

    if first_run:
        print(f"  Ilk kurulum: {len(videos[:5])} mevcut video islenmis sayilacak")
        for video in videos[:5]:
            fp = compute_fingerprint(video["title"], 0)
            processed[video["video_id"]] = {
                "title": video["title"],
                "channel": channel_info["name"],
                "detected_at": datetime.now().isoformat(),
                "fingerprint": fp,
                "skipped_initial": True,
            }
        save_processed(processed)
        return []

    for video in videos[:5]:
        vid = video["video_id"]

        if vid in processed:
            continue

        if DUPLICATE_CHECK:
            title_fp = compute_fingerprint(video["title"], 0)
            dup_vid = find_duplicate(title_fp, processed)
            if dup_vid:
                dup_title = processed[dup_vid].get("title", "?")
                print(f"  MUKERRER: {video['title'][:40]}...")
                print(f"    Ayni icerik daha once yuklendi: [{dup_vid}] {dup_title[:40]}")
                processed[vid] = {
                    "title": video["title"],
                    "channel": channel_info["name"],
                    "detected_at": datetime.now().isoformat(),
                    "fingerprint": title_fp,
                    "status": "duplicate_skipped",
                    "duplicate_of": dup_vid,
                }
                continue

        print(f"  [YENI!] {video['title'][:60]}...")
        new_videos.append({
            "channel_key": channel_key,
            "channel_name": channel_info["name"],
            "video": video,
        })

        fp = compute_fingerprint(video["title"], 0)
        processed[vid] = {
            "title": video["title"],
            "channel": channel_info["name"],
            "detected_at": datetime.now().isoformat(),
            "fingerprint": fp,
        }

    save_processed(processed)
    return new_videos


def check_all_channels():
    print(f"{'='*60}")
    print(f"YOUTUBE YENI VIDEO KONTROLU")
    print(f"Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    all_new = []
    for key in CHANNELS:
        new = check_channel(key)
        all_new.extend(new)

    print(f"\n{'='*60}")
    print(f"SONUC: {len(all_new)} yeni video bulundu")
    print(f"{'='*60}")
    return all_new