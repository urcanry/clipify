import io
import json
import subprocess

from config import MAX_VIDEO_HEIGHT

YTDLP_EXTRA = [
    "--js-runtimes", "node",
    "--remote-components", "ejs:github",
    "--extractor-args", "youtube:player_client=web_embedded",
]


def _base_cmd():
    return ["yt-dlp", *YTDLP_EXTRA]


def get_video_info(url):
    cmd = _base_cmd() + [
        "--dump-json",
        "--no-download",
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"HATA: Video bilgisi alinamadi: {result.stderr[:200]}")
        return None
    return json.loads(result.stdout)


def download_to_memory(url, max_height=MAX_VIDEO_HEIGHT):
    cmd = _base_cmd() + [
        "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b*",
        "--merge-output-format", "webm",
        "--no-playlist",
        "--no-progress",
        "-o", "-",
        url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60 * 60,
            check=False,
        )
        if result.returncode != 0:
            print(f"HATA: Indirme basarisiz: {result.stderr.decode('utf-8', errors='replace')[:300]}")
            return None
        if not result.stdout:
            print("HATA: Indirilen veri bos")
            return None
        size_mb = len(result.stdout) / (1024 * 1024)
        print(f"  Ram'e indirildi: {size_mb:.1f} MB (bellek, disk yazilmadi)")
        return io.BytesIO(result.stdout)
    except subprocess.TimeoutExpired:
        print("HATA: Indirme zaman asimina ugradi")
        return None
    except Exception as e:
        print(f"HATA: Indirme hatasi: {e}")
        return None