import hashlib
import random
import re

from config import CONTACT_EMAIL, YOUTUBE_TAGS, INTRO_FILE

CHANNEL_NAMES = ["rraenee", "raenee", "rr aenee", "elraenn", "craftest", "cfyt", "zovek", "2kan", "2kan"]

STOP_WORDS = {
    "izliyor", "izledi", "izliyorum", "tepki", "reaksiyon", "reaction", "reacts",
    "video", "yayın", "canlı", "stream", "part", "bölüm", "full", "vod", "v2",
    "watch", "watching", "with", "ve", "the", "of", "bir", "yeni", "ne", "kim",
    "izliyoruz", "tepkisi", "reaksiyonu", "tepkileri", "emoji", "wow", "moments",
    "en", "iyi", "best", "top", "funny", "komik", "episode",
}

MOODS = [
    "Tepkileriyle", "Anında Patlayan Tepkiler", "Klasik Lezzet", "Ustasından",
    "Kahkaha Garantili", "Gözünden Kaçmadı", "Zirveye Oynuyor", "Açık Ara Farkla",
    "Saniye Saniye", "İlk Kez", "Efsane Anlar", "Kesit", "Koltuk Tepkisi",
]

TITLE_TEMPLATES = [
    "Rraenee {kw} Anlamında {mood}",
    "Rraenee React: {kw}",
    "Rraenee Bu {kw} Yüzünden {mood}",
    "{mood} | Rraenee {kw}",
    "Rraenee {kw} İzlerken {mood}",
    "Cüneyt Fonuyla Rraenee {kw}",
    "Rraenee {kw} Skeçleri ve {mood}",
    "VOD'dan {kw} Kesiti - Rraenee {mood}",
]

OPENING_HOOKS = [
    "Bu kesitte Rraenee'nin uzun yayın VOD'larından öne çıkan anları bir araya getirdik.",
    "Rraenee'nin arşivinden derlediğimiz {kw} temalı kesit burada.",
    "Yayın arşivimin en güzel {kw} anlarını tek videoda topladım.",
]

DESC_BULLETS = [
    "İçerik orijinal yayıncının VOD arşivinden kısa kesit halinde düzenlenmiştir.",
    "Anlık tepkiler ve uzun sohbetlerden derlenmiştir.",
    "Yayıncıya ait telifli görüntüler; kesit özet olarak paylaşılır.",
    "Bu kanal kesit ve reaksiyon içeriklerine odaklanır.",
]


def _seed(video_id):
    h = hashlib.sha256((video_id or "x").encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _clean_title(title):
    t = (title or "").lower()
    t = re.sub(r"#[^\s#]+", " ", t)
    t = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ\s]", " ", t)
    for name in CHANNEL_NAMES:
        t = re.sub(rf"\b{re.escape(name)}\b", " ", t)
    words = [w for w in t.split() if w and w not in STOP_WORDS]
    return words


def generate_kw(video_id, title):
    words = _clean_title(title)
    if not words:
        words = ["Efsane"]
    limit = min(3, len(words))
    picked = words[:limit]
    return " ".join(w.capitalize() for w in picked)


def generate_title(video_id, title, channel_name, intro_end):
    kw = generate_kw(video_id, title)
    random.seed(_seed(video_id))
    template = random.choice(TITLE_TEMPLATES)
    mood = random.choice(MOODS)
    rendered = template.format(kw=kw, mood=mood)
    rendered = re.sub(r"\s+", " ", rendered).strip()
    if len(rendered) > 95:
        rendered = rendered[:95].rstrip()
    if len(rendered) < 12:
        rendered = f"Rraenee {kw} - Kesit"
    return rendered


def generate_description(video_id, title, channel_name, intro_end, original_url=""):
    kw = generate_kw(video_id, title)
    random.seed(_seed(video_id) ^ 0x9E3779B9)

    base_hook = random.choice(OPENING_HOOKS).format(kw=kw)
    body_bullets = random.sample(DESC_BULLETS, k=min(3, len(DESC_BULLETS)))

    tags_str = ", ".join(["#clipify", "#rraenee", *random.sample(YOUTUBE_TAGS, k=min(3, len(YOUTUBE_TAGS)))])

    desc = (
        base_hook + "\n\n"
    )
    for i, bullet in enumerate(body_bullets, 1):
        desc += f"{i}. {bullet}\n"
    desc += "\n"
    desc += (
        "──────────────────────\n"
        "Bu kanal bağımsız bir kesit/reaksiyon kanalıdır ve içerikler "
        "YouTube'un telif politikalarına uygun olarak yeniden düzenlenmektedir.\n"
    )
    if original_url:
        desc += f"Orijinal Video: {original_url}\n"
    if channel_name:
        desc += f"Kaynak Kanal: {channel_name}\n"
    desc += (
        "──────────────────────\n"
        f"📩 İletişim & Telif: {CONTACT_EMAIL}\n\n"
        f"{tags_str}"
    )
    return desc


def generate_tags(title, channel_name):
    words = _clean_title(title)
    tags = list(YOUTUBE_TAGS)
    seen = set(tags)
    for w in words[:6]:
        if w not in seen:
            tags.append(w)
            seen.add(w)
    return tags[:30]