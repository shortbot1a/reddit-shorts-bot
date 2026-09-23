# Guía de configuración: Bot de Shorts de Reddit

La versión completa e interactiva de esta guía está aquí:
https://claude.ai/code/artifact/7fcf594d-99d4-480f-9d4b-7ff8144548b7
(ojo: esa versión aún describe el plan original con una VM en Oracle Cloud;
el plan actual usa GitHub Actions, ver pasos 6-8 abajo y `SECRETS_SETUP.md`).

Este archivo es una copia de referencia rápida para tenerla también dentro
del proyecto. Resumen de los 8 pasos:

1. **Reddit**: no tienes que hacer nada ahora mismo — el proyecto arranca en
   modo RSS (`REDDIT_MODE=rss`), que no necesita cuenta de desarrollador
   (Reddit exige aprobación manual desde 2026 para el acceso vía API).
   Opcional, para mejorar el filtrado más adelante: pide acceso en
   https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164,
   y si te lo aprueban, crea la app en https://www.reddit.com/prefs/apps
   (tipo "script"), copia `client_id` / `client_secret` a `config/.env` y
   cambia `REDDIT_MODE=api`.
2. **Pexels / Pixabay**: claves gratuitas en https://www.pexels.com/api/ y
   https://pixabay.com/api/docs/, pégalas en `config/.env`.
3. **Google Cloud**: crea proyecto, activa "YouTube Data API v3", configura
   la pantalla de consentimiento OAuth (tipo Externo, y **publícala** para
   que el token no caduque cada 7 días), crea dos credenciales OAuth tipo
   "Desktop app" (una por canal) y descarga los JSON como
   `config/client_secret_en.json` y `config/client_secret_es.json`.
4. **Canales de YouTube**: crea los dos canales (EN y ES) desde la misma
   cuenta de Google.
5. **Autorizar OAuth** (en tu ordenador, no en la VM):
   `python src/authorize_youtube.py en` y luego `... es`. Copia
   `token_en.json` / `token_es.json` a `config/` en la VM.
6. **Hosting (GitHub Actions, gratis, sin tarjeta)**: en vez de una VM, el
   pipeline corre en GitHub Actions según un horario (cada 8h). No hace falta
   servidor propio. Ver `SECRETS_SETUP.md` para los pasos exactos: crear el
   repositorio, subir el código y añadir las claves como "Secrets" de GitHub
   (Reddit, Pexels/Pixabay, y los 4 archivos de YouTube).
7. **Validar en local antes de subir** (opcional pero recomendado): rellena
   `config/.env` en tu ordenador con los mismos valores que vas a poner como
   Secrets, y ejecuta `python src/validate_config.py` para confirmar que todo
   funciona antes de dejarlo en manos del cron de GitHub Actions.
8. **Primera ejecución de prueba**: en GitHub, pestaña "Actions" → workflow
   "Reddit Shorts Bot" → botón "Run workflow", para lanzarlo a mano y ver los
   logs sin esperar a la siguiente hora programada.

Riesgos a vigilar y preguntas frecuentes: están en la versión completa
(enlace arriba).
