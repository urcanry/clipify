import io
import os

from config import INTRO_FILE, OUTPUT_FPS

from ffmpeg_utils import run_ffmpeg_pipe, probe_dimensions


def _scale_filter(w, h, fps):
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )


def load_intro_bytes():
    if not os.path.exists(INTRO_FILE):
        return None, True
    try:
        with open(INTRO_FILE, "rb") as f:
            return f.read(), False
    except Exception:
        return None, True


def render_final(video_bytes, intro_end, fallback_size=(1920, 1080)):
    w, h = probe_dimensions(video_bytes)
    if not w or not h:
        w, h = fallback_size
    w, h = int(w) & ~1, int(h) & ~1
    fps = OUTPUT_FPS

    intro_bytes, intro_missing = load_intro_bytes()
    if intro_missing:
        print(f"  UYARI: '{INTRO_FILE}' bulunamadi. Intro eklenmedi, video yeniden kodlandi.")

        scale = _scale_filter(w, h, fps)
        args = [
            "-i", "pipe:0",
            "-filter_complex",
            (
                f"[0:v]{scale}[vo];"
                f"[0:a]atrim=start={intro_end},asetpts=PTS-STARTPTS,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[ao]"
            ),
            "-map", "[vo]", "-map", "[ao]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+empty_moov+frag_keyframe",
            "-f", "mp4", "pipe:1",
        ]
    else:
        scale_i = _scale_filter(w, h, fps)
        scale_c = _scale_filter(w, h, fps)
        args = [
            "-i", INTRO_FILE,
            "-i", "pipe:0",
            "-filter_complex",
            (
                f"[0:v]{scale_i}[iv];"
                f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[ia];"
                f"[1:v]trim=start={intro_end},setpts=PTS-STARTPTS,{scale_c}[cv];"
                f"[1:a]atrim=start={intro_end},asetpts=PTS-STARTPTS,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[ca];"
                f"[iv][ia][cv][ca]concat=n=2:v=1:a=1[vo][ao]"
            ),
            "-map", "[vo]", "-map", "[ao]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+empty_moov+frag_keyframe",
            "-f", "mp4", "pipe:1",
        ]

    try:
        out = run_ffmpeg_pipe(args, input_bytes=video_bytes, timeout=2 * 60 * 60)
    except RuntimeError as e:
        print(f"  HATA: Video isleme basarisiz: {e}")
        return None

    if out:
        size_mb = len(out) / (1024 * 1024)
        print(f"  Render tamam: {size_mb:.1f} MB (RAM'de, intro {'eklendi' if not intro_missing else 'eklenmedi'})")
    return out


def generate_preview(video_bytes, max_duration=60, max_width=1280):
    height = int(max_width * 9 / 16) // 2 * 2
    args = [
        "-i", "pipe:0",
        "-t", str(max_duration),
        "-vf",
        f"scale={max_width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={max_width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps=24",
        "-c:v", "libx264", "-preset", "fast", "-crf", "26",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+empty_moov+frag_keyframe",
        "-f", "mp4", "pipe:1",
    ]
    try:
        out = run_ffmpeg_pipe(args, input_bytes=video_bytes, timeout=15 * 60)
    except RuntimeError as e:
        print(f"  UYARI: Preview olusturulamadi: {e}")
        return None
    if out:
        size_mb = len(out) / (1024 * 1024)
        print(f"  Preview: {size_mb:.1f} MB ({max_duration}s)")
    return out
