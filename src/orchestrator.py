"""
orchestrator.py
----------------
Punto de entrada único del pipeline. Se ejecuta vía cron en la VM (ver
deploy/) y hace todo el trabajo de un "run" sin intervención:

  1. Busca candidatos nuevos en Reddit (ya filtrados y no usados antes).
  2. Para cada candidato (hasta cubrir el objetivo diario por canal):
       a. Genera narración + vídeo en inglés -> sube al canal EN.
       b. Traduce el texto -> genera narración + vídeo en español -> sube al canal ES.
       c. Marca la historia como usada y registra el resultado en la BD.
  3. Si algo falla a mitad de una historia, se registra el error y se sigue
     con la siguiente candidata: un fallo puntual nunca detiene el sistema.

Diseñado para funcionar sin supervisión: todos los errores quedan en
logs/orchestrator.log y en la base de datos (tabla run_log / uploads).
"""

from __future__ import annotations

import os
import sys
import logging
import traceback
from pathlib import Path
from datetime import datetime

from env_utils import load_env

sys.path.insert(0, str(Path(__file__).resolve().parent))

import state_db
import reddit_source
import translator
import tts
import subtitles
import footage_bank
import compose_video
import youtube_upload

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"

CHANNEL_EN = "youtube_en"
CHANNEL_ES = "youtube_es"


def _setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"orchestrator_{datetime.utcnow():%Y%m%d}.log"
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
    )


logger = logging.getLogger("orchestrator")


def _build_metadata(candidate: reddit_source.Candidate, lang: str, title_text: str) -> dict:
    category_labels = {
        "en": {
            "dilemma": "Reddit Story", "relationship": "Relationship Story",
            "horror": "Scary Story", "confession": "Confession",
            "story": "Reddit Story",
        },
        "es": {
            "dilemma": "Historia de Reddit", "relationship": "Historia de Pareja",
            "horror": "Historia de Terror", "confession": "Confesión",
            "story": "Historia de Reddit",
        },
    }
    label = category_labels[lang].get(candidate.category, "Reddit Story")
    if lang == "en":
        title = f"{title_text.strip()[:80]} #shorts"
        description = (
            f"{label} narrated from r/{candidate.subreddit}.\n"
            f"Original post: {candidate.permalink}\n\n"
            f"#redditstories #shorts #storytime"
        )
    else:
        title = f"{title_text.strip()[:80]} #shorts"
        description = (
            f"{label} narrada, traducida y adaptada desde r/{candidate.subreddit}.\n"
            f"Post original (en inglés): {candidate.permalink}\n\n"
            f"#historiasdereddit #shorts #reddit"
        )
    tags = [candidate.subreddit, candidate.category, "reddit", "shorts"]
    return {"title": title, "description": description, "tags": tags}


def _produce_and_upload(candidate: reddit_source.Candidate, lang: str, channel: str,
                         title_text: str, body_text: str) -> tuple[bool, str | None]:
    story_dir = OUTPUT_DIR / candidate.post_id
    story_dir.mkdir(parents=True, exist_ok=True)

    narration_text = f"{title_text}. {body_text}"
    audio_path = story_dir / f"narration_{lang}.mp3"
    ass_path = story_dir / f"subs_{lang}.ass"
    video_path = story_dir / f"final_{lang}.mp4"

    tts.synthesize(narration_text, lang, audio_path)
    words = subtitles.transcribe_words(audio_path, lang)
    if not words:
        raise RuntimeError("Whisper no devolvió palabras; audio posiblemente vacío o silencioso.")
    subtitles.build_ass_karaoke(words, ass_path)

    audio_duration = words[-1].end + 0.5
    clip, offset = footage_bank.pick_background_clip(audio_duration)
    compose_video.compose(clip, offset, audio_path, ass_path, video_path)

    meta = _build_metadata(candidate, lang, title_text)
    video_id = youtube_upload.upload_short(
        video_path, lang, meta["title"], meta["description"], meta["tags"]
    )
    return True, video_id


def run_once():
    load_env()
    _setup_logging()
    state_db.init_db()
    footage_bank.refresh_footage_bank()

    target_per_channel = int(os.getenv("VIDEOS_PER_DAY_PER_CHANNEL", 3))
    run_id = state_db.start_run()
    attempted = uploaded = failed = 0

    en_remaining = target_per_channel - state_db.uploads_today(CHANNEL_EN)
    es_remaining = target_per_channel - state_db.uploads_today(CHANNEL_ES)
    needed = max(en_remaining, es_remaining)

    if needed <= 0:
        logger.info("Ya se alcanzó el objetivo diario en ambos canales. Nada que hacer.")
        state_db.finish_run(run_id, 0, 0, 0, "objetivo diario ya cumplido")
        return

    logger.info("Objetivo: %d historias nuevas (EN pendientes=%d, ES pendientes=%d)",
                needed, max(en_remaining, 0), max(es_remaining, 0))

    candidates = reddit_source.fetch_candidates(max_results=needed * 3)
    if not candidates:
        logger.warning("No se encontraron candidatos nuevos que pasen los filtros hoy.")
        state_db.finish_run(run_id, 0, 0, 0, "sin candidatos")
        return

    processed_stories = 0
    for candidate in candidates:
        if processed_stories >= needed:
            break
        logger.info("=== Historia: [%s] %s (%d upvotes) ===",
                    candidate.subreddit, candidate.title, candidate.score)

        story_ok_once = False

        if en_remaining > 0:
            attempted += 1
            try:
                ok, video_id = _produce_and_upload(candidate, "en", CHANNEL_EN,
                                                    candidate.title, candidate.body)
                uploaded += 1
                story_ok_once = True
                state_db.record_upload(candidate.post_id, "en", CHANNEL_EN, "uploaded", video_id)
                en_remaining -= 1
            except Exception as exc:
                failed += 1
                logger.error("Fallo generando/subiendo versión EN de %s: %s\n%s",
                             candidate.post_id, exc, traceback.format_exc())
                state_db.record_upload(candidate.post_id, "en", CHANNEL_EN, "failed", error=str(exc))

        if es_remaining > 0:
            attempted += 1
            try:
                title_es, body_es = translator.translate_story(candidate.title, candidate.body)
                ok, video_id = _produce_and_upload(candidate, "es", CHANNEL_ES, title_es, body_es)
                uploaded += 1
                story_ok_once = True
                state_db.record_upload(candidate.post_id, "es", CHANNEL_ES, "uploaded", video_id)
                es_remaining -= 1
            except Exception as exc:
                failed += 1
                logger.error("Fallo generando/subiendo versión ES de %s: %s\n%s",
                             candidate.post_id, exc, traceback.format_exc())
                state_db.record_upload(candidate.post_id, "es", CHANNEL_ES, "failed", error=str(exc))

        # Marcamos la historia como usada tanto si tuvo éxito como si falló en
        # ambos idiomas, para no reintentar indefinidamente el mismo post
        # problemático (un post roto no debe bloquear el pipeline para siempre).
        state_db.mark_post_used(candidate.post_id, candidate.subreddit, candidate.title,
                                 candidate.category, candidate.score)
        if story_ok_once:
            processed_stories += 1

    notes = f"procesadas={processed_stories}/{needed}"
    state_db.finish_run(run_id, attempted, uploaded, failed, notes)
    logger.info("Run terminado. Intentos=%d Subidos=%d Fallidos=%d (%s)",
                attempted, uploaded, failed, notes)


if __name__ == "__main__":
    run_once()
