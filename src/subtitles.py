"""
subtitles.py
------------
Genera subtítulos palabra-por-palabra con Whisper corriendo en local
(faster-whisper: motor CTranslate2, gratis, sin límite de uso, sin conexión
tras la primera descarga del modelo) y los convierte en un archivo .ass con
efecto "karaoke" (barrido de color palabra a palabra), que es el formato
estándar que usa libass/FFmpeg para este tipo de animación.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from dataclasses import dataclass

from faster_whisper import WhisperModel

logger = logging.getLogger("subtitles")

_MODEL_CACHE: dict[str, WhisperModel] = {}

FONT_NAME = "Poppins"
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Máximo de palabras por línea en pantalla (más corto = más legible en 9:16)
MAX_WORDS_PER_LINE = 4


@dataclass
class Word:
    text: str
    start: float
    end: float


def _get_model() -> WhisperModel:
    size = os.getenv("WHISPER_MODEL_SIZE", "small")
    if size not in _MODEL_CACHE:
        logger.info("Cargando modelo Whisper local '%s' (solo la primera vez de cada proceso)...", size)
        _MODEL_CACHE[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[size]


def transcribe_words(audio_path: str | Path, lang: str) -> list[Word]:
    """Transcribe el audio ya narrado y devuelve timestamps por palabra.
    Como el audio lo generamos nosotros mismos (TTS), esto es básicamente
    un "forced alignment" de alta precisión, no un reconocimiento a ciegas."""
    model = _get_model()
    segments, _info = model.transcribe(
        str(audio_path),
        language=lang,
        word_timestamps=True,
        vad_filter=True,  # evita transcribir silencios/ruido de fondo
    )
    words: list[Word] = []
    for segment in segments:
        for w in (segment.words or []):
            words.append(Word(text=w.word.strip(), start=w.start, end=w.end))
    return words


def _group_lines(words: list[Word], max_words: int = MAX_WORDS_PER_LINE) -> list[list[Word]]:
    lines, current = [], []
    for w in words:
        current.append(w)
        ends_sentence = w.text.endswith((".", "!", "?"))
        if len(current) >= max_words or ends_sentence:
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    return lines


def _ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


ASS_HEADER_TEMPLATE = """[Script Info]
Title: Reddit Shorts Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{fontsize},&H00FFFFFF,&H0000D7FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},2,2,60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass_karaoke(words: list[Word], out_path: str | Path,
                       fontsize: int = 90, outline: int = 6, marginv: int = 700) -> Path:
    """Construye un .ass con efecto karaoke: cada línea corta (2-4 palabras)
    aparece centrada y se va "iluminando" palabra a palabra en color acento
    (naranja/dorado) sobre blanco, siguiendo el ritmo real de la narración."""
    out_path = Path(out_path)
    lines = _group_lines(words)

    body = []
    for line in lines:
        if not line:
            continue
        start = line[0].start
        end = line[-1].end
        # Tags \k en centésimas de segundo, duración de cada palabra dentro de la línea
        k_tags = ""
        for w in line:
            dur_cs = max(1, round((w.end - w.start) * 100))
            text = w.text.replace("{", "").replace("}", "")
            k_tags += f"{{\\k{dur_cs}}}{text} "
        body.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Karaoke,,0,0,0,,{k_tags.strip()}"
        )

    header = ASS_HEADER_TEMPLATE.format(font=FONT_NAME, fontsize=fontsize, outline=outline, marginv=marginv)
    out_path.write_text(header + "\n".join(body) + "\n", encoding="utf-8")
    return out_path


def generate_subtitles(audio_path: str | Path, lang: str, out_ass_path: str | Path) -> Path:
    words = transcribe_words(audio_path, lang)
    if not words:
        raise RuntimeError(f"Whisper no devolvió palabras para {audio_path}; revisa el audio de entrada.")
    return build_ass_karaoke(words, out_ass_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level="INFO")
    audio = sys.argv[1] if len(sys.argv) > 1 else "output/test_en.mp3"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    out = generate_subtitles(audio, lang, "output/test_en.ass")
    print("Subtítulos generados en:", out)
