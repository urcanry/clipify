import io
import subprocess
import re

import numpy as np


def run_ffmpeg_pipe(args, input_bytes=None, timeout=60 * 60):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    try:
        result = subprocess.run(
            cmd,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(err[-500:])
        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg zaman asimi")


def probe_dimensions(input_bytes):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        "-i", "pipe:0",
    ]
    try:
        result = subprocess.run(cmd, input=input_bytes, capture_output=True, timeout=120)
        if result.returncode == 0:
            parts = result.stdout.decode("utf-8", errors="replace").strip().split(",")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


def probe_has_audio(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0:
            return bool(result.stdout.decode("utf-8", errors="replace").strip())
    except Exception:
        pass
    return False


def probe_duration_file(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0:
            val = result.stdout.decode("utf-8", errors="replace").strip()
            if val:
                return float(val)
    except Exception:
        pass
    return None


def decode_audio_numpy(input_bytes, seconds=90):
    cmd = [
        "-i", "pipe:0",
        "-t", str(seconds),
        "-vn",
        "-f", "s16le",
        "-ar", "16000",
        "-ac", "1",
        "pipe:1",
    ]
    try:
        pcm = run_ffmpeg_pipe(cmd, input_bytes=input_bytes, timeout=300)
    except RuntimeError:
        return None
    if not pcm:
        return None
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def silence_detect(input_bytes, seconds=90, noise_db=-40, d=0.5):
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", "pipe:0",
        "-t", str(seconds),
        "-af", f"silencedetect=noise={noise_db}dB:d={d}",
        "-f", "null", "-",
    ]
    result = subprocess.run(
        cmd,
        input=input_bytes,
        capture_output=True,
        timeout=300,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    return [float(t) for t in re.findall(r"silence_start:\s*([\d.]+)", stderr)]


def scene_detect(input_bytes, seconds=90, threshold=0.4):
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", "pipe:0",
        "-t", str(seconds),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(
        cmd,
        input=input_bytes,
        capture_output=True,
        timeout=300,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", stderr)]


def read_audio_for_first_seconds(input_bytes, seconds=90):
    return decode_audio_numpy(input_bytes, seconds=seconds)


def bytesio_from_bytes(data):
    buf = io.BytesIO(data)
    buf.seek(0)
    return buf