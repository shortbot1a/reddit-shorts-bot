"""
validate_config.py
-------------------
Comprobación rápida de que toda la configuración está lista ANTES de dejar
el pipeline corriendo solo. Ejecútalo con:

    venv/bin/python src/validate_config.py

No sube nada a YouTube ni gasta cuota: solo verifica que las claves existen,
que Reddit responde, y que los tokens de YouTube son válidos.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))


def check(label: str, ok: bool, hint: str = ""):
    status = "✅" if ok else "❌"
    print(f"{status} {label}" + (f"  -> {hint}" if not ok and hint else ""))
    return ok


def main():
    load_dotenv()
    all_ok = True

    reddit_mode = os.getenv("REDDIT_MODE", "rss").strip().lower()
    check(f"Modo de extracción de Reddit: '{reddit_mode}'", True)

    if reddit_mode == "api":
        all_ok &= check("REDDIT_CLIENT_ID configurado", bool(os.getenv("REDDIT_CLIENT_ID")),
                         "Rellena config/.env con tus credenciales de https://www.reddit.com/prefs/apps")
        all_ok &= check("REDDIT_CLIENT_SECRET configurado", bool(os.getenv("REDDIT_CLIENT_SECRET")))
        if os.getenv("REDDIT_CLIENT_ID"):
            try:
                import reddit_source
                reddit = reddit_source._reddit_client()
                next(reddit.subreddit("test").hot(limit=1))
                check("Conexión con la API de Reddit", True)
            except Exception as exc:
                all_ok &= check("Conexión con la API de Reddit", False, str(exc))
    else:
        try:
            import reddit_source
            sample = reddit_source.fetch_candidates_rss(max_results=1)
            check("Conexión con los feeds RSS de Reddit", True,
                  f"({len(sample)} candidato(s) de prueba encontrado(s))")
        except Exception as exc:
            all_ok &= check("Conexión con los feeds RSS de Reddit", False, str(exc))

    all_ok &= check("PEXELS_API_KEY configurado", bool(os.getenv("PEXELS_API_KEY")),
                     "Consíguela gratis en https://www.pexels.com/api/")
    all_ok &= check("PIXABAY_API_KEY configurado (opcional pero recomendado)",
                     bool(os.getenv("PIXABAY_API_KEY")))

    for lang in ("en", "es"):
        secret_file = os.getenv(f"YT_{lang.upper()}_CLIENT_SECRET_FILE", "")
        token_file = os.getenv(f"YT_{lang.upper()}_TOKEN_FILE", "")
        all_ok &= check(f"client_secret del canal {lang.upper()} presente",
                         Path(secret_file).exists() if secret_file else False,
                         f"Descárgalo de Google Cloud Console y guárdalo en {secret_file}")
        has_token = Path(token_file).exists() if token_file else False
        all_ok &= check(f"Token OAuth del canal {lang.upper()} presente",
                         has_token,
                         f"Ejecuta: python src/authorize_youtube.py {lang}")
        if has_token:
            try:
                import youtube_upload
                service = youtube_upload._get_service(lang)
                service.channels().list(part="id", mine=True).execute()
                check(f"Token OAuth del canal {lang.upper()} válido", True)
            except Exception as exc:
                all_ok &= check(f"Token OAuth del canal {lang.upper()} válido", False, str(exc))

    print("\n" + ("Todo listo. Puedes dejar el cron corriendo." if all_ok
                  else "Faltan cosas por configurar (revisa los ❌ de arriba)."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
