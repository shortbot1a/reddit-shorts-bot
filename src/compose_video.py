"""
compose_video.py
-----------------
Composición final con FFmpeg: fondo (recortado a la duración del audio) +
narración + subtítulos karaoke quemados, en vertical 1080x1920 (9:16), listo
para subir a YouTube Shorts.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("compose_video")

TARGET_W, TARGET_H = 1080, 1920
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _escape_ffmpeg_path(path: str) -> str:
    """Escapa una ruta para usarla dentro de un argumento de filtro de FFmpeg
    (filter_complex), donde ':' y '\\' son caracteres especiales."""
    p = str(path).replace("\\", "\\\\").replace(":", "\\:")
    return p


def _get_duration(path: str | Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def compose(
    background_path: str | Path,
    background_offset: float,
    audio_path: str | Path,
    subtitles_ass_path: str | Path,
    out_path: str | Path,
    dim_background: float = 0.55,
) -> Path:
    """
    - background_path: clip de fondo (cualquier resolución/orientación)
    - background_offset: segundos desde donde empezar a recortar el fondo
    - audio_path: narración ya generada (TTS)
    - subtitles_ass_path: subtítulos karaoke (.ass) ya generados con subtitles.py
    - dim_background: 0.0-1.0, cuánto oscurecer el fondo para que se lea mejor
      el texto (0.55 = deja pasar el 55% del brillo original)
    """
    background_path = Path(background_path)
    audio_path = Path(audio_path)
    subtitles_ass_path = Path(subtitles_ass_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    audio_duration = _get_duration(audio_path)
    bg_duration = _get_duration(background_path)

    needs_loop = bg_duration < (background_offset + audio_duration)

    ass_escaped = _escape_ffmpeg_path(str(subtitles_ass_path))
    fonts_escaped = _escape_ffmpeg_path(str(FONTS_DIR))

    # 1) Escala + recorte centrado a 1080x1920 manteniendo relación de aspecto
    #    ("cover" crop, igual que object-fit: cover en CSS).
    # 2) Oscurecemos un poco el fondo (eq=brightness) para que el texto blanco
    #    con borde resalte sobre cualquier vídeo.
    # 3) Quemamos los subtítulos karaoke (.ass) con nuestra fuente propia.
    vf = (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H},"
        f"eq=brightness={-(1 - dim_background) * 0.5}:contrast=1.05,"
        f"ass='{ass_escaped}':fontsdir='{fonts_escaped}'"
    )

    cmd = ["ffmpeg", "-y"]
    if needs_loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", f"{background_offset:.2f}", "-i", str(background_path)]
    cmd += ["-i", str(audio_path)]
    cmd += [
        "-t", f"{audio_duration:.2f}",
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", "30",
        "-c:a", "aac", "-b:a", "160k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path),
    ]

    logger.info("Componiendo vídeo final: %s", out_path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg stderr:\n%s", result.stderr[-4000:])
        raise RuntimeError(f"FFmpeg falló componiendo {out_path}")
    return out_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level="INFO")
    bg, offset, audio, ass, out = sys.argv[1:6]
    compose(bg, float(offset), audio, ass, out)
    print("Vídeo generado:", out)
