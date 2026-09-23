"""
youtube_upload.py
------------------
Sube el vídeo final al canal de YouTube correspondiente vía API oficial
(gratuita). Usa las credenciales OAuth generadas una vez con
authorize_youtube.py y las renueva automáticamente en cada ejecución.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger("youtube_upload")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]

# Categoría "Entertainment" de YouTube
DEFAULT_CATEGORY_ID = "24"
MAX_SHORT_SECONDS = 180  # YouTube considera Short hasta 3 minutos (vertical + #Shorts)


class YouTubeUploadError(Exception):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, HttpError):
        # No reintentamos errores de cuota agotada ni de permisos: hay que
        # arreglarlos a mano, reintentar solo tapa el problema.
        return exc.resp.status in (500, 502, 503, 504)
    return isinstance(exc, (ConnectionError, TimeoutError))


def _get_service(lang: str):
    token_file = os.environ[f"YT_{lang.upper()}_TOKEN_FILE"]
    if not Path(token_file).exists():
        raise YouTubeUploadError(
            f"No existe {token_file}. Ejecuta primero authorize_youtube.py {lang} "
            f"en tu ordenador y copia el token a la VM."
        )
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(token_file).write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def _get_video_duration(path: str | Path) -> float:
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=5, min=5, max=60),
       retry=retry_if_exception(_is_retryable), reraise=True)
def upload_short(
    video_path: str | Path,
    lang: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "public",
) -> str:
    """Sube `video_path` al canal configurado para `lang` ('en' o 'es').
    Devuelve el videoId de YouTube."""
    video_path = Path(video_path)
    duration = _get_video_duration(video_path)
    if duration > MAX_SHORT_SECONDS:
        logger.warning(
            "El vídeo dura %.0fs, por encima del límite recomendado de Shorts (%ds). "
            "Se subirá igualmente pero puede no clasificarse como Short.",
            duration, MAX_SHORT_SECONDS,
        )

    # "#Shorts" en título/descripción ayuda a YouTube a clasificarlo como Short
    if "#shorts" not in title.lower() and "#shorts" not in description.lower():
        description = description.rstrip() + "\n\n#Shorts"

    service = _get_service(lang)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:15],
            "categoryId": DEFAULT_CATEGORY_ID,
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    logger.info("Subiendo '%s' al canal %s...", title, lang)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Progreso subida: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    logger.info("Subido correctamente: https://youtube.com/watch?v=%s", video_id)
    return video_id


if __name__ == "__main__":
    import sys
    logging.basicConfig(level="INFO")
    path, lang, title = sys.argv[1], sys.argv[2], sys.argv[3]
    vid = upload_short(path, lang, title, "Vídeo de prueba subido por el pipeline.", tags=["reddit", "shorts"])
    print("videoId:", vid)
