import requests

from config import INTRO_METHOD, INTRO_MAX_DURATION, INTRO_MIN_DURATION, INTRO_FIXED_SECONDS, WHISPER_MODEL

from ffmpeg_utils import silence_detect, scene_detect, decode_audio_numpy


def detect_intro_end(video_id, video_bytes, duration, method="auto"):
    if method == "fixed" and INTRO_FIXED_SECONDS:
        print(f"  Intro: sabit saniye = {INTRO_FIXED_SECONDS}s")
        return float(INTRO_FIXED_SECONDS)

    if method == "auto":
        result = _try_sponsorblock(video_id)
        if result is not None:
            print(f"  Intro: SponsorBlock = {result:.1f}s")
            return result

        result = _try_silence(video_bytes)
        if result is not None:
            print(f"  Intro: Sessizlik algilama = {result:.1f}s")
            return result

        result = _try_whisper(video_bytes)
        if result is not None:
            print(f"  Intro: Whisper ilk konusma = {result:.1f}s")
            return result

        result = _try_scene(video_bytes)
        if result is not None:
            print(f"  Intro: Sahne degisimi = {result:.1f}s")
            return result

        fallback = INTRO_FIXED_SECONDS or 0
        print(f"  Intro: Tum yontemler basarisiz, fallback = {fallback}s")
        return float(fallback)

    if method == "sponsorblock":
        result = _try_sponsorblock(video_id)
        if result is not None:
            return result
        return float(INTRO_FIXED_SECONDS or 0)

    if method == "whisper":
        result = _try_whisper(video_bytes)
        if result is not None:
            return result
        return float(INTRO_FIXED_SECONDS or 0)

    if method == "scene":
        result = _try_scene(video_bytes)
        if result is not None:
            return result
        return float(INTRO_FIXED_SECONDS or 0)

    if method == "silence":
        result = _try_silence(video_bytes)
        if result is not None:
            return result
        return float(INTRO_FIXED_SECONDS or 0)

    return float(INTRO_FIXED_SECONDS or 0)


def _try_sponsorblock(video_id):
    try:
        url = "https://sponsor.ajay.app/api/skipSegments"
        params = {"videoID": video_id, "categories": '["intro"]'}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        for segment in data or []:
            if segment.get("category") == "intro":
                end = segment["segment"][1]
                if INTRO_MIN_DURATION <= end <= INTRO_MAX_DURATION:
                    return end
        return None
    except Exception:
        return None


def _try_whisper(video_bytes):
    audio = decode_audio_numpy(video_bytes, seconds=90)
    if audio is None or len(audio) == 0:
        return None

    try:
        import numpy as np
        if np.abs(audio).max() < 1e-4:
            return None
    except Exception:
        pass

    try:
        import whisper
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(audio, language="tr", verbose=False)
        first_segment = _first_real_segment(result)
        if first_segment is not None and INTRO_MIN_DURATION <= first_segment <= INTRO_MAX_DURATION:
            return first_segment
        return None
    except Exception:
        return None


def _first_real_segment(result):
    skip_words = {"music", "müzik", "♪", "♫", "applause", "alkış", "[music]", "[applause]", "[music playing]"}
    for seg in result.get("segments", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if text.lower() in skip_words:
            continue
        return float(seg.get("start", 0))
    return None


def _try_silence(video_bytes):
    try:
        for s in silence_detect(video_bytes, seconds=90):
            if INTRO_MIN_DURATION <= s <= INTRO_MAX_DURATION:
                return s
        return None
    except Exception:
        return None


def _try_scene(video_bytes):
    try:
        for t in scene_detect(video_bytes, seconds=90):
            if INTRO_MIN_DURATION <= t <= INTRO_MAX_DURATION:
                return t
        return None
    except Exception:
        return None