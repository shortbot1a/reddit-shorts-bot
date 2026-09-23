"""
tts.py
------
Narración por voz sintética, 100% gratis:

  1º intento: Edge-TTS (voces neuronales de Microsoft Edge, gratis y sin
     límite documentado, pero es un servicio NO oficial/no soportado — puede
     fallar o cambiar sin aviso).
  2º intento (fallback automático): Piper TTS, un motor 100% open-source que
     corre completamente en local. Es la red de seguridad: si Edge-TTS deja
     de funcionar algún día, el pipeline NO se detiene, solo baja algo la
     calidad de la voz hasta que se revise.

Piper necesita los modelos de voz (.onnx) descargados una vez; se guardan en
assets/voices/ y no se vuelven a descargar salvo que se borren.
"""

from __future__ import annotations

import os
import asyncio
import logging
from pathlib import Path

import edge_tts
import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger("tts")

VOICES_DIR = Path(__file__).resolve().parent.parent / "assets" / "voices"

EDGE_VOICES = {
    "en": os.getenv("TTS_VOICE_EN", "en-US-ChristopherNeural"),
    "es": os.getenv("TTS_VOICE_ES", "es-ES-AlvaroNeural"),
}

# Modelos Piper (voces medianas, buen compromiso calidad/tamaño). Se descargan
# de la CDN oficial de Piper (Hugging Face) la primera vez.
PIPER_VOICES = {
    "en": {
        "onnx": "en_US-lessac-medium.onnx",
        "json": "en_US-lessac-medium.onnx.json",
        "base_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/",
    },
    "es": {
        "onnx": "es_ES-davefx-medium.onnx",
        "json": "es_ES-davefx-medium.onnx.json",
        "base_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/",
    },
}


class TTSError(Exception):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_fixed(3),
       retry=retry_if_exception_type(Exception), reraise=True)
async def _edge_tts_synthesize(text: str, voice: str, out_path: Path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise TTSError("Salida de Edge-TTS vacía o demasiado pequeña")


def _ensure_piper_voice(lang: str) -> tuple[Path, Path]:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    cfg = PIPER_VOICES[lang]
    onnx_path = VOICES_DIR / cfg["onnx"]
    json_path = VOICES_DIR / cfg["json"]
    for fname, path in ((cfg["onnx"], onnx_path), (cfg["json"], json_path)):
        if not path.exists():
            logger.info("Descargando voz Piper %s (solo la primera vez)...", fname)
            r = requests.get(cfg["base_url"] + fname, timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
    return onnx_path, json_path


def _piper_synthesize(text: str, lang: str, out_path: Path):
    from piper.voice import PiperVoice
    import wave

    onnx_path, _json_path = _ensure_piper_voice(lang)
    voice = PiperVoice.load(str(onnx_path))
    with wave.open(str(out_path), "wb") as wav_file:
        # piper-tts==1.2.0 (versión fijada en requirements.txt) expone el
        # método synthesize(), no synthesize_wav() (eso es de versiones más
        # nuevas de la librería). Con la versión equivocada, wav_file nunca
        # recibe setnchannels/setframerate y wave.close() explota con
        # "# channels not specified", enmascarando el AttributeError real.
        voice.synthesize(text, wav_file)


def synthesize(text: str, lang: str, out_path: str | Path) -> Path:
    """Genera un archivo de audio narrado para `text` en el idioma `lang`
    ('en' o 'es'). Intenta Edge-TTS primero; si falla, usa Piper local."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = EDGE_VOICES[lang]

    try:
        asyncio.run(_edge_tts_synthesize(text, voice, out_path))
        logger.info("Narración generada con Edge-TTS (%s)", voice)
        return out_path
    except Exception as exc:
        logger.warning("Edge-TTS falló (%s). Usando Piper local como respaldo.", exc)

    try:
        _piper_synthesize(text, lang, out_path.with_suffix(".wav"))
        if out_path.suffix != ".wav":
            # Normalizamos a mp3 para mantener el resto del pipeline uniforme
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(out_path.with_suffix(".wav")), str(out_path)],
                check=True, capture_output=True,
            )
        logger.info("Narración generada con Piper (fallback local)")
        return out_path
    except Exception as exc:
        raise TTSError(f"Fallaron ambos motores TTS (Edge-TTS y Piper): {exc}") from exc


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    p = synthesize("This is a quick test of the narration pipeline.", "en", "output/test_en.mp3")
    print("Generado:", p)
