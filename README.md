# Reddit Shorts Bot

Sistema automatizado que genera y publica YouTube Shorts verticales a partir
de historias de Reddit narradas por voz sintética, con subtítulos karaoke
sincronizados, en dos canales (inglés y español). 100% gratuito, sin
suscripciones: todas las piezas usan tiers gratuitos permanentes o software
local/open-source.

**Para la guía de configuración paso a paso (lo que tienes que hacer tú),
lee `GUIA_CONFIGURACION.md`** o la versión interactiva enlazada ahí.

## Decisión de arquitectura: dos canales, no pistas multi-idioma

La API de YouTube (Data API v3) **no permite** añadir pistas de audio
multi-idioma a un vídeo por API — esa función solo existe manualmente en
YouTube Studio. Por eso, y porque además decidiste usar dos canales
separados (uno EN, uno ES) en vez de concentrar señales en uno solo, cada
historia se procesa una vez y se sube dos veces: la versión en inglés al
canal EN, la versión traducida al canal ES.

## Aviso importante: acceso a la API de Reddit (añadido tras el lanzamiento)

Reddit introdujo en 2026 la "Responsible Builder Policy": crear una app en
`reddit.com/prefs/apps` ya no es autoservicio instantáneo, requiere
aprobación manual que puede tardar o ser denegada. Por eso el sistema
soporta dos modos, controlados por `REDDIT_MODE` en `config/.env`:

- `rss` (por defecto): lee los feeds RSS públicos de cada subreddit. No
  necesita aprobación ni credenciales de Reddit, funciona desde ya. Filtrado
  más débil: no hay upvotes reales (se usa la posición en "top de la
  semana/mes" como proxy) ni flair oficial, y la detección de NSFW es una
  heurística de palabras clave, no el campo oficial de Reddit. Revisa a mano
  los primeros vídeos generados en este modo.
- `api`: usa PRAW con credenciales OAuth propias, mejor filtrado (upvotes
  reales, NSFW oficial, flair). Requiere que Reddit apruebe tu app — ver
  `GUIA_CONFIGURACION.md`, Paso 1.

Cambiar de un modo a otro es solo una línea en `config/.env`, no requiere
tocar código.

## Arquitectura

```
Reddit (PRAW) → filtro calidad/NSFW/dedupe → traducción local (Argos)
     → TTS (Edge-TTS + fallback Piper) → subtítulos palabra-a-palabra
     (faster-whisper local) → ASS karaoke → composición FFmpeg 9:16
     → subida YouTube (canal EN / canal ES) → SQLite (estado/dedupe)
```

| Módulo | Archivo | Qué hace |
| --- | --- | --- |
| Extracción/filtrado | `src/reddit_source.py` | Candidatos de Reddit, filtros de calidad/NSFW/repost |
| Traducción | `src/translator.py` | EN↔ES offline con Argos Translate (sin coste, sin API de pago) |
| Narración | `src/tts.py` | Edge-TTS + fallback Piper local |
| Subtítulos | `src/subtitles.py` | faster-whisper local, timestamps por palabra, genera `.ass` karaoke |
| Banco de vídeo | `src/footage_bank.py` | Descarga y cachea clips CC0 de Pexels/Pixabay |
| Composición | `src/compose_video.py` | FFmpeg: recorte 9:16, subtítulos quemados, mezcla de audio |
| Subida | `src/youtube_upload.py` | OAuth por canal, subida resumable, reintentos |
| Estado | `src/state_db.py` | SQLite: posts usados, historial de subidas, cuotas diarias |
| Orquestador | `src/orchestrator.py` | Punto de entrada; corre todo el pipeline por historia |
| Autorización | `src/authorize_youtube.py` | Script de un solo uso para autorizar cada canal |
| Validación | `src/validate_config.py` | Comprueba que toda la configuración está lista |

## Probado en desarrollo

El paso más delicado (composición de vídeo 9:16 + subtítulos karaoke
quemados con FFmpeg) se probó de extremo a extremo con datos sintéticos
(fondo generado y texto con timestamps simulados) y produjo un vídeo válido
1080x1920 a 30fps con el efecto karaoke funcionando correctamente.

Los pasos que necesitan acceso a internet sin restricciones (llamadas reales
a Reddit/Pexels/Pixabay/Edge-TTS/YouTube, y la descarga de los modelos de
Whisper/Argos/Piper la primera vez) no se pudieron probar en el entorno de
desarrollo por política de red del sandbox, pero el código se compiló e
importó sin errores, y esas mismas librerías son las oficiales/estándar de
cada servicio. La VM de Oracle Cloud tendrá acceso normal a internet, así
que funcionarán en el primer arranque real. Ejecuta
`venv/bin/python src/validate_config.py` tras la configuración para
confirmarlo antes de dejarlo desatendido.

## Comandos útiles

```bash
# Validar que toda la configuración está lista
venv/bin/python src/validate_config.py

# Ejecutar el pipeline manualmente una vez (fuera del cron)
venv/bin/python src/orchestrator.py

# Ver los últimos logs
tail -f logs/orchestrator_*.log

# Ver el estado (posts usados, subidas) con sqlite3
sqlite3 state/pipeline.db "select * from uploads order by id desc limit 10;"
```

## Ajustar sin tocar código

- `config/.env`: claves, número de vídeos/día por canal, tamaño del modelo Whisper.
- `config/subreddits.yaml`: subreddits fuente, upvotes mínimos, flairs excluidos.
