"""
env_utils.py
------------
Carga config/.env de forma robusta desde cualquier script del proyecto,
sin importar desde qué carpeta se ejecute.

Por qué existe: `load_dotenv()` (sin argumentos) solo busca un archivo
llamado ".env" en el directorio actual o en sus carpetas padre - NO mira
dentro de config/, aunque ahí es donde vive nuestro .env real. Esto causó
dos bugs distintos con el mismo origen:
  - En Windows, authorize_youtube.py fallaba con KeyError hasta que se puso
    un .env "suelto" junto al script (fuera de config/).
  - En GitHub Actions, el workflow escribe las claves en config/.env, pero
    el pipeline nunca las veía (PEXELS_API_KEY/PIXABAY_API_KEY "no
    configuradas") porque nadie miraba dentro de config/.

Esta función carga primero un .env en la raíz del proyecto si existe (para
quien prefiera tenerlo así en su ordenador), y SIEMPRE también carga
config/.env si existe, sin pisar valores que ya estuvieran definidos.
Funciona en los dos escenarios a la vez sin que el usuario tenga que hacer
nada especial.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env():
    load_dotenv()  # .env en la raíz / cwd, si existe (uso local histórico)
    load_dotenv(PROJECT_ROOT / "config" / ".env", override=False)
