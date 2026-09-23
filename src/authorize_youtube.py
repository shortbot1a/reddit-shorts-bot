"""
authorize_youtube.py
---------------------
Script de AUTORIZACIÓN ÚNICA (one-time) para cada canal de YouTube.

Este script necesita abrir un navegador de verdad para que inicies sesión y
aceptes el permiso, así que se ejecuta UNA VEZ en tu ordenador (portátil/PC),
no en el servidor/VM donde correrá el pipeline. El resultado es un archivo
pequeño (token_en.json o token_es.json) que luego copias a la VM. A partir
de ahí, el sistema se renueva solo sin volver a pedir login (salvo que
revoques el acceso desde tu cuenta de Google).

Uso:
    python authorize_youtube.py en   # autoriza el canal en inglés
    python authorize_youtube.py es   # autoriza el canal en español

Requisitos previos (ver GUIA_CONFIGURACION.md):
    - Haber creado el proyecto en Google Cloud y activado "YouTube Data API v3"
    - Haber descargado el archivo client_secret_en.json / client_secret_es.json
      desde Google Cloud Console y haberlo puesto en config/
    - Haber iniciado sesión en el navegador con la cuenta de Google dueña del
      canal correspondiente ANTES de ejecutar este script
"""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
import os

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import load_env

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def authorize(lang: str):
    load_env()
    client_secret_file = os.environ[f"YT_{lang.upper()}_CLIENT_SECRET_FILE"]
    token_file = os.environ[f"YT_{lang.upper()}_TOKEN_FILE"]

    if not Path(client_secret_file).exists():
        print(f"ERROR: no encuentro {client_secret_file}. Revisa la guía de configuración, "
              f"paso 'Google Cloud / YouTube API', y coloca ahí el archivo descargado.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    # run_local_server abre tu navegador automáticamente y espera el login+consentimiento
    creds = flow.run_local_server(port=0, prompt="consent")

    Path(token_file).write_text(creds.to_json(), encoding="utf-8")
    print(f"\n✅ Autorización guardada en {token_file}")
    print("   Copia este archivo a la VM en la misma ruta (config/) y ya está.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("en", "es"):
        print("Uso: python authorize_youtube.py en|es")
        sys.exit(1)
    authorize(sys.argv[1])
