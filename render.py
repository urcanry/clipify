import io
import os
import tempfile

from config import INTRO_FILE, OUTPUT_FPS, LOGO_FILE

from ffmpeg_utils import run_ffmpeg_pipe, probe_dimensions, probe_duration_file, probe_has_audio


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

    scale_i = _scale_filter(w, h, fps)
    scale_c = _scale_filter(w, h, fps)
    aformat = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    vcodec = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
    acodec = ["-c:a", "aac", "-b:a", "192k"]

    tmp_in = None
    tmp_out = None
    try:
        try:
            fd_in, tmp_in = tempfile.mkstemp(suffix=".mp4")
            os.close(fd_in)
            with open(tmp_in, "wb") as f:
                f.write(video_bytes)
            fd_out, tmp_out = tempfile.mkstemp(suffix=".mp4")
            os.close(fd_out)
        except OSError as e:
            print(f"  HATA: Gecici dosya olusturulamadi: {e}")
            return None

        _, intro_missing = load_intro_bytes()

        if intro_missing:
            print(f"  UYARI: '{INTRO_FILE}' bulunamadi. Intro eklenmedi, video yeniden kodlandi.")
            filter_complex = (
                f"[0:v]{scale_i}[vo];"
                f"[0:a]atrim=start={intro_end},asetpts=PTS-STARTPTS,{aformat}[ao]"
            )
            inputs = ["-i", tmp_in]
            if os.path.exists(LOGO_FILE):
                inputs += ["-i", LOGO_FILE]
                filter_complex += (
                    f";[1:v]scale=110:110:force_original_aspect_ratio=decrease[lg];"
                    f"[vo][lg]overlay=W-w-16:16[vof]"
                )
            out_label = "vof" if os.path.exists(LOGO_FILE) else "vo"
            args = [
                *inputs,
                "-filter_complex", filter_complex,
                "-map", f"[{out_label}]", "-map", "[ao]",
                *vcodec, *acodec,
                tmp_out,
            ]
        else:
            intro_dur = probe_duration_file(INTRO_FILE) or 2.0
            intro_has_audio = probe_has_audio(INTRO_FILE)
            if intro_has_audio:
                filter_complex = (
                    f"[0:v]{scale_i}[iv];"
                    f"[0:a]{aformat}[ia];"
                    f"[1:v]trim=start={intro_end},setpts=PTS-STARTPTS,{scale_c}[cv];"
                    f"[1:a]atrim=start={intro_end},asetpts=PTS-STARTPTS,{aformat}[ca];"
                    f"[iv][ia][cv][ca]concat=n=2:v=1:a=1[vo][ao]"
                )
            else:
                filter_complex = (
                    f"[0:v]{scale_i}[iv];"
                    f"[1:v]trim=start={intro_end},setpts=PTS-STARTPTS,{scale_c}[cv];"
                    f"[1:a]atrim=start={intro_end},asetpts=PTS-STARTPTS,{aformat}[ca];"
                    f"aevalsrc=0:s=48000:c=stereo:d={intro_dur},asetpts=PTS-STARTPTS,{aformat}[ia];"
                    f"[iv][ia][cv][ca]concat=n=2:v=1:a=1[vo][ao]"
                )
            inputs = ["-i", INTRO_FILE, "-i", tmp_in]
            if os.path.exists(LOGO_FILE):
                inputs += ["-i", LOGO_FILE]
                filter_complex += (
                    f";[2:v]scale=110:110:force_original_aspect_ratio=decrease[lg];"
                    f"[vo][lg]overlay=W-w-16:16[vof]"
                )
            out_label = "vof" if os.path.exists(LOGO_FILE) else "vo"
            args = [
                *inputs,
                "-filter_complex", filter_complex,
                "-map", f"[{out_label}]", "-map", "[ao]",
                *vcodec, *acodec,
                tmp_out,
            ]

        try:
            run_ffmpeg_pipe(args, input_bytes=None, timeout=2 * 60 * 60)
        except RuntimeError as e:
            print(f"  HATA: Video isleme basarisiz: {e}")
            return None

        with open(tmp_out, "rb") as f:
            out = f.read()
    finally:
        for p in (tmp_in, tmp_out):
            if p and os.path.exists(p):
                os.remove(p)

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


def generate_gif(video_bytes, start, duration, max_width=480, fps=10):
    height = int(max_width * 9 / 16) // 2 * 2
    args = [
        "-i", "pipe:0",
        "-ss", str(max(0, start)),
        "-t", str(duration),
        "-vf",
        f"fps={fps},scale={max_width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={max_width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
        "-loop", "0",
        "-c:v", "gif",
        "-f", "gif", "pipe:1",
    ]
    try:
        out = run_ffmpeg_pipe(args, input_bytes=video_bytes, timeout=15 * 60)
    except RuntimeError as e:
        print(f"  UYARI: GIF olusturulamadi ({start}s): {e}")
        return None
    if out:
        size_kb = len(out) / 1024
        print(f"  GIF ({start:.0f}s): {size_kb:.0f} KB")
    return out
