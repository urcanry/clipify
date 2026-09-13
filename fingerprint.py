import hashlib
import re

CHANNEL_NAMES = [
    "rraenee", "raenee", "rr aenee", "elraenn",
    "craftest", "cfyt", "zovek", "2kan",
]

NOISE_WORDS = {
    "izliyor", "izledi", "izliyorum", "tepkisi", "reaksiyon", "reaction",
    "reacts", "tepkileri", "reaksiyonu", "izliyorum",
}

DURATION_BUCKET = 30


def normalize_title(title):
    t = (title or "").lower()
    t = re.sub(r"#[^\s#]+", " ", t)
    t = re.sub(r"[^\wçğıöşü\s]", " ", t)
    for name in CHANNEL_NAMES:
        t = re.sub(rf"\b{re.escape(name)}\b", " ", t)
    words = [w for w in t.split() if w and w not in NOISE_WORDS and (len(w) > 1 or w.isdigit())]
    return " ".join(words)


def bucket_duration(duration):
    return round((duration or 0) / DURATION_BUCKET) * DURATION_BUCKET


def compute_fingerprint(title, duration):
    norm = normalize_title(title)
    if not norm:
        norm = "unknown"
    bucketed = bucket_duration(duration)
    raw = f"{norm}|{bucketed}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def find_duplicate(fingerprint, processed_db):
    if not fingerprint:
        return None
    for vid, entry in processed_db.items():
        if entry.get("fingerprint") == fingerprint:
            return vid
    return None