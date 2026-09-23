"""
footage_bank.py
----------------
Banco local de vídeos de fondo genuinamente libres de derechos.

Importante (ver aviso de riesgo entregado al usuario): NO usamos clips de
"gameplay sin copyright" de dudosa procedencia (mucho de ese contenido en
realidad sí tiene copyright del estudio del videojuego, y el reuploader que
dice "libre de derechos" no tiene autoridad para cederlo). En su lugar:

  - Pexels API y Pixabay API: bancos de vídeo con licencia gratuita que
    permite explícitamente uso comercial y modificación, sin atribución
    obligatoria. Tier gratuito permanente, con API key gratis.
  - Categorías por defecto: parkour/naturaleza/ciudad/abstracto/drone -
    visualmente dinámico (igual que el "gameplay" cumple la función de
    retener la vista) pero sin ningún riesgo de copyright de videojuego.

Los clips se descargan una vez a assets/footage/<categoria>/ y se
reutilizan indefinidamente recortando fragmentos aleatorios según la
duración del audio narrado.
"""

from __future__ import annotations

import os
import random
import logging
import subprocess
from pathlib import Path

import requests

logger = logging.getLogger("footage_bank")

FOOTAGE_DIR = Path(__file__).resolve().parent.parent / "assets" / "footage"

DEFAULT_QUERIES = [
    "parkour", "freerunning", "drone city", "nature timelapse",
    "abstract background loop", "extreme sports", "underwater",
]

MIN_CLIPS_PER_QUERY = 4


def _pexels_search_and_download(query: str, n: int):
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        logger.warning("PEXELS_API_KEY no configurada, saltando Pexels.")
        return
    out_dir = FOOTAGE_DIR / query.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("*.mp4"))
    if len(existing) >= n:
        return

    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params={"query": query, "orientation": "portrait", "per_page": n, "size": "medium"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    for i, video in enumerate(data.get("videos", [])):
        # Elegimos el archivo vertical de mayor resolución disponible
        files = sorted(video["video_files"], key=lambda f: f.get("height", 0), reverse=True)
        vertical = next((f for f in files if f.get("height", 0) >= f.get("width", 1)), files[0])
        dest = out_dir / f"pexels_{video['id']}.mp4"
        if dest.exists():
            continue
        logger.info("Descargando clip de Pexels: %s (%s)", query, video["id"])
        r = requests.get(vertical["link"], timeout=60)
        r.raise_for_status()
        dest.write_bytes(r.content)


def _pixabay_search_and_download(query: str, n: int):
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        logger.warning("PIXABAY_API_KEY no configurada, saltando Pixabay.")
        return
    out_dir = FOOTAGE_DIR / query.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("*.mp4"))
    if len(existing) >= n:
        return

    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": api_key, "q": query, "per_page": n},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    for hit in data.get("hits", []):
        dest = out_dir / f"pixabay_{hit['id']}.mp4"
        if dest.exists():
            continue
        video_url = hit["videos"]["medium"]["url"]
        logger.info("Descargando clip de Pixabay: %s (%s)", query, hit["id"])
        r = requests.get(video_url, timeout=60)
        r.raise_for_status()
        dest.write_bytes(r.content)


def refresh_footage_bank(queries: list[str] | None = None, n_per_query: int = MIN_CLIPS_PER_QUERY):
    """Rellena el banco local si faltan clips. Se puede llamar en cada
    ejecución: si ya hay suficientes clips descargados, no hace nada (0
    llamadas de red), así que no consume cuota de las APIs de stock salvo
    la primera vez o cuando decidas ampliar categorías."""
    for q in (queries or DEFAULT_QUERIES):
        try:
            _pexels_search_and_download(q, n_per_query)
            _pixabay_search_and_download(q, n_per_query)
        except Exception as exc:
            logger.warning("No se pudo refrescar el banco de '%s': %s", q, exc)


def _video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def pick_background_clip(target_duration: float) -> tuple[Path, float]:
    """Elige un clip aleatorio del banco local lo bastante largo, y devuelve
    (ruta, offset_de_inicio) para recortar `target_duration` segundos desde
    un punto aleatorio (así aunque se reutilice el mismo clip varias veces,
    no se ve siempre el mismo fragmento)."""
    all_clips = list(FOOTAGE_DIR.rglob("*.mp4"))
    if not all_clips:
        raise RuntimeError(
            "El banco de vídeos de fondo está vacío. Ejecuta refresh_footage_bank() "
            "primero (necesita PEXELS_API_KEY y/o PIXABAY_API_KEY configuradas)."
        )
    random.shuffle(all_clips)
    for clip in all_clips:
        try:
            duration = _video_duration(clip)
        except Exception:
            continue
        if duration > target_duration + 1:
            max_offset = duration - target_duration - 0.5
            offset = random.uniform(0, max_offset)
            return clip, offset
    # Si ningún clip individual es tan largo como el audio, devolvemos el más
    # largo disponible; compose_video.py se encarga de hacer loop si hace falta.
    longest = max(all_clips, key=lambda c: _video_duration(c))
    return longest, 0.0


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    refresh_footage_bank()
    clip, offset = pick_background_clip(30)
    print(f"Clip elegido: {clip} (offset {offset:.1f}s)")
