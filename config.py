import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def _env_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


DEFAULT_CHANNELS = {
    "Craftest": {
        "id": "UCRXsu9ORjM6F-LjBRDXF2lw",
        "name": "Craftest",
        "intro_method": "auto",
        "intro_override": None,
    },
    "cFyt": {
        "id": "UC3E_eF5GHqA05nPPm1riHYg",
        "name": "cFyt",
        "intro_method": "auto",
        "intro_override": None,
    },
    "Zovek": {
        "id": "UCbp3D9GpQbHNTj6glCbUlsQ",
        "name": "Zovek",
        "intro_method": "auto",
        "intro_override": None,
    },
    "2kan": {
        "id": "UCDsJphAxtcoBIRMM49jWYBg",
        "name": "2kan",
        "intro_method": "auto",
        "intro_override": None,
    },
}


def _load_channels():
    env = os.getenv("CHANNELS_JSON")
    if env:
        try:
            data = json.loads(env)
            channels = {}
            for key, val in data.items():
                channels[key] = {
                    "id": val.get("id", val if isinstance(val, str) else ""),
                    "name": val.get("name", key),
                    "intro_method": val.get("intro_method", "auto"),
                    "intro_override": val.get("intro_override"),
                }
            return channels
        except (ValueError, AttributeError):
            pass
    return DEFAULT_CHANNELS


CHANNELS = _load_channels()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8643672758")

INTRO_METHOD = os.getenv("INTRO_METHOD", "auto")
INTRO_MAX_DURATION = _env_int("INTRO_MAX_DURATION", 60)
INTRO_MIN_DURATION = _env_int("INTRO_MIN_DURATION", 3)
INTRO_FIXED_SECONDS = _env_int("INTRO_FIXED_SECONDS", 25)

INTRO_FILE = os.path.join(BASE_DIR, "YouTube Intro.mp4")
LOGO_FILE = os.getenv("LOGO_FILE", os.path.join(BASE_DIR, "logo.jpg"))

MIN_VIDEO_DURATION = _env_int("MIN_VIDEO_DURATION", 300)
MAX_VIDEO_DURATION = _env_int("MAX_VIDEO_DURATION", 7200)
MAX_VIDEO_HEIGHT = _env_int("MAX_VIDEO_HEIGHT", 1080)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
OUTPUT_FPS = _env_int("OUTPUT_FPS", 30)

AUTO_UPLOAD = _env_bool("AUTO_UPLOAD", True)
IN_MEMORY = _env_bool("IN_MEMORY", True)
DUPLICATE_CHECK = _env_bool("DUPLICATE_CHECK", True)

YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "private")
YOUTUBE_CATEGORY = os.getenv("YOUTUBE_CATEGORY", "24")
YOUTUBE_TAGS = [t.strip() for t in os.getenv("YOUTUBE_TAGS", "").split(",") if t.strip()] or [
    "reaksiyon", "kesit", "clipify", "rraenee"
]

TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
THUMBNAIL_DIR = os.path.join(BASE_DIR, "thumbnails")
KAPAK_DIR = os.path.join(BASE_DIR, "Kapaklar")
DATA_DIR = os.path.join(BASE_DIR, "data")

PROCESSED_FILE = os.path.join(DATA_DIR, "processed.json")
UPLOADS_FILE = os.path.join(DATA_DIR, "uploads.json")

MONITOR_INTERVAL = _env_int("MONITOR_INTERVAL", 300)
MAX_VIDEO_SIZE_MB = _env_int("MAX_VIDEO_SIZE_MB", 4000)

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "clipify@example.com")