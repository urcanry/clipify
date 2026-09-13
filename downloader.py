import io
import json
import subprocess
import threading
import time

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
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        chunks = []
        total = 0
        started = time.time()

        def drain_stderr(p):
            for line in p.stderr:
                line = line.decode("utf-8", errors="replace").strip()
                if line:
                    print(f"  [yt-dlp] {line}")

        reader = threading.Thread(target=drain_stderr, args=(proc,), daemon=True)
        reader.start()

        while True:
            chunk = proc.stdout.read(1024 * 256)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            elapsed = time.time() - started
            mb = total / (1024 * 1024)
            if elapsed > 0:
                rate = mb / elapsed
                print(f"\r  Indiriliyor: {mb:.1f} MB @ {rate:.1f} MB/s", end="", flush=True)

        print()
        proc.wait()
        reader.join(timeout=2)

        if proc.returncode != 0:
            print("HATA: Indirme basarisiz")
            return None
        if total == 0:
            print("HATA: Indirilen veri bos")
            return None

        data = b"".join(chunks)
        print(f"  Ram'e indirildi: {len(data) / (1024 * 1024):.1f} MB (bellek, disk yazilmadi)")
        return io.BytesIO(data)

    except Exception as e:
        print(f"HATA: Indirme hatasi: {e}")
        return None