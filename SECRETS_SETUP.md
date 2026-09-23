# Poner el bot a correr en GitHub Actions (gratis, sin tarjeta)

Esta es la guía definitiva para la parte final: subir el proyecto a GitHub y
dejarlo corriendo solo cada 8 horas, sin servidor propio y sin dar ningún
dato de pago. Tarda unos 15-20 minutos la primera vez.

## Por qué así

GitHub Actions deja ejecutar código bajo un horario ("cron"). En un
repositorio **público**, las ejecuciones son gratis e ilimitadas (en uno
privado, gratis hasta 2.000 minutos al mes, de sobra para 3 ejecuciones al
día). No hace falta tarjeta para la cuenta gratuita de GitHub ni para usar
Actions dentro de esos límites.

Las claves y contraseñas **nunca van dentro del código** que se sube al
repositorio (por eso puede ser público sin problema): se guardan aparte,
cifradas, como "Secrets" del repositorio, y el propio workflow las coloca en
su sitio (`config/.env`, `config/token_en.json`, etc.) justo antes de cada
ejecución, dentro de la máquina temporal de GitHub, que se borra entera al
terminar.

## Paso 1 — Claves gratuitas que aún te faltan

Si no las tienes ya, consíguelas (ambas gratis, sin tarjeta, 2 minutos cada
una):

- **Pexels**: entra en https://www.pexels.com/api/ , inicia sesión o
  regístrate, y copia la "API Key" que te dan.
- **Pixabay**: entra en https://pixabay.com/api/docs/ , inicia sesión o
  regístrate, y copia tu API key (aparece arriba de la página de docs, ya
  logueado).

Guárdalas en un sitio temporal (un Bloc de notas), las necesitarás en el
Paso 4.

## Paso 2 — Crear el repositorio en GitHub

1. Entra en https://github.com/new (con tu cuenta ya creada).
2. Nombre sugerido: `reddit-shorts-bot` (puede ser otro).
3. Visibilidad: **Public** (para minutos ilimitados gratis; si prefieres
   Private también funciona, con el límite de 2.000 min/mes).
4. No marques ninguna casilla de "Add a README" ni ".gitignore" (el proyecto
   ya trae los suyos).
5. Pulsa "Create repository". GitHub te mostrará una página con comandos:
   déjala abierta, la usamos en el Paso 3.

## Paso 3 — Subir el código

Yo preparo el código (ya lo tengo listo: workflow de GitHub Actions,
`.gitignore` correcto para que las claves nunca se suban, etc.) y te lo doy
para que lo subas tú mismo con estos comandos, o lo subo yo si me confirmas
que puedo usar `git push` en tu ordenador.

Si lo haces tú: abre una terminal en la carpeta del proyecto y ejecuta (
cambia la URL por la que te dio GitHub en el Paso 2):

```
git init
git add .
git commit -m "Bot de Shorts de Reddit"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/reddit-shorts-bot.git
git push -u origin main
```

## Paso 4 — Añadir los Secrets

En tu repositorio de GitHub: **Settings → Secrets and variables → Actions →
New repository secret**. Crea uno por cada fila de esta tabla (el nombre
exacto a la izquierda, tal cual, en mayúsculas):

| Nombre del Secret        | Qué pegar |
|---------------------------|-----------|
| `PEXELS_API_KEY`          | Tu clave de Pexels (Paso 1) |
| `PIXABAY_API_KEY`         | Tu clave de Pixabay (Paso 1) |
| `YT_CLIENT_SECRET_EN`     | Todo el contenido del archivo `config/client_secret_en.json` |
| `YT_CLIENT_SECRET_ES`     | Todo el contenido del archivo `config/client_secret_es.json` |
| `YT_TOKEN_EN`             | Todo el contenido del archivo `config/token_en.json` |
| `YT_TOKEN_ES`             | Todo el contenido del archivo `config/token_es.json` |

Para los 4 últimos: abre cada archivo `.json` con el Bloc de notas, selecciona
todo (Ctrl+A), copia (Ctrl+C), y pégalo entero como valor del Secret
correspondiente. Son los mismos archivos que ya tienes en
`Descargas\reddit-shorts-bot-auth\config\` de cuando autorizamos los canales.

**Importante**: esta parte tienes que hacerla tú — por seguridad, no debo
escribir tokens ni contraseñas en ningún formulario, ni siquiera en el de
GitHub, así que no puedo rellenar los Secrets por ti aunque me des permiso.

Opcional (solo si en el futuro Reddit te aprueba acceso a su API, ver
`GUIA_CONFIGURACION.md` paso 1): añade también `REDDIT_CLIENT_ID` y
`REDDIT_CLIENT_SECRET` — el workflow detecta automáticamente que existen y
cambia de modo RSS a modo API sin que toques nada más.

## Paso 5 — Probar

En tu repositorio: pestaña **Actions** → selecciona el workflow "Reddit
Shorts Bot" en la barra lateral → botón **Run workflow** (arriba a la
derecha) → **Run workflow** de nuevo para confirmar.

Se pondrá en marcha ahí mismo; puedes hacer clic en la ejecución para ver el
progreso en vivo, paso a paso. La primera vez tarda más (descarga el modelo
de traducción, las voces, los clips de vídeo), las siguientes son más
rápidas gracias a la caché.

Si algo falla, la ejecución se marca en rojo y puedes abrir cada paso para
ver el error exacto — cuéntamelo y lo arreglamos.

## Después de esto

Una vez la primera ejecución de prueba suba un vídeo correctamente a los dos
canales, ya no hace falta tocar nada más: el workflow se dispara solo cada 8
horas (`0 */8 * * *`, hora UTC) para siempre, gratis.
