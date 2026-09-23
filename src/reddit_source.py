"""
reddit_source.py
-----------------
Extrae posts candidatos de Reddit y aplica los filtros de calidad/seguridad
antes de pasarlos al resto del pipeline.

Dos modos, controlados por REDDIT_MODE en config/.env:

  - "api" (ideal, pero requiere aprobación de Reddit desde 2026 por su
    "Responsible Builder Policy" — ya no es autoservicio instantáneo):
    usa PRAW con tus credenciales OAuth. Mejor filtrado (upvotes reales,
    NSFW oficial, flair).

  - "rss" (modo por defecto mientras no tengas la app aprobada): lee los
    feeds RSS públicos de cada subreddit, que no requieren autenticación ni
    aprobación. Filtrado más débil (sin upvotes reales, sin flair, y la
    detección de NSFW es una heurística, no el campo oficial), así que se
    recomienda revisar a mano los primeros vídeos generados en este modo.

Ambos modos devuelven la misma clase Candidate, así que el resto del
pipeline (orchestrator.py) no necesita saber cuál se está usando.
"""

from __future__ import annotations

import os
import re
import time
import logging
from dataclasses import dataclass

import yaml
import requests
from dotenv import load_dotenv

from state_db import is_post_used

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("reddit_source")

REPOST_PATTERNS = re.compile(
    r"\b(repost|cross[- ]?post|x-post|not my story|found this on|stolen from)\b",
    re.IGNORECASE,
)
REMOVED_MARKERS = {"[removed]", "[deleted]", ""}

# Heurística de defensa en profundidad para el modo RSS, que no tiene acceso
# al campo oficial "over_18". Los subreddits configurados ya son
# comunidades SFW de por sí, esto es una capa extra, no la única barrera.
NSFW_KEYWORD_PATTERN = re.compile(
    r"\b(nsfw|18\+|nudity|porn|explicit sexual)\b", re.IGNORECASE
)

RSS_USER_AGENT = "reddit-shorts-bot-rss/1.0 (personal, low-volume, non-commercial script)"


@dataclass
class Candidate:
    post_id: str
    subreddit: str
    category: str
    title: str
    body: str
    score: int              # en modo 'rss' es un rango sintético (posición en el listado), no upvotes reales
    permalink: str
    score_is_estimated: bool = False

    @property
    def word_count(self) -> int:
        return len((self.title + " " + self.body).split())


def _load_subreddit_config(path: str = "config/subreddits.yaml") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["subreddits"]


def _looks_like_repost_or_nsfw(title: str, body: str) -> bool:
    text = f"{title} {body}"
    if REPOST_PATTERNS.search(text):
        return True
    if NSFW_KEYWORD_PATTERN.search(text):
        return True
    return False


# ---------------------------------------------------------------------------
# MODO RSS (sin aprobación de Reddit, funciona ya)
# ---------------------------------------------------------------------------

_ID_FROM_REDDIT_ID = re.compile(r"t3_([a-z0-9]+)", re.IGNORECASE)
_ID_FROM_URL = re.compile(r"/comments/([a-z0-9]+)/", re.IGNORECASE)


def _extract_short_id(entry) -> str | None:
    raw_id = getattr(entry, "id", "") or ""
    m = _ID_FROM_REDDIT_ID.search(raw_id)
    if m:
        return m.group(1)
    link = getattr(entry, "link", "") or ""
    m = _ID_FROM_URL.search(link)
    if m:
        return m.group(1)
    return None


def _clean_rss_body(html: str) -> str:
    """El HTML de cada entrada RSS de Reddit trae el texto del post seguido
    de un pie 'submitted by ... [link] [comments]'. Nos quedamos solo con el
    texto real del post."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")

    # Quitamos el pie: es el último <span> que contiene un enlace [link] o [comments]
    for span in soup.find_all("span"):
        span_text = span.get_text(strip=True).lower()
        if "[link]" in span_text or "[comments]" in span_text:
            span.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    # Restos típicos que a veces sobreviven al recorte anterior
    text = re.sub(r"submitted by\s*/?u/\S+\s*(to\s*/?r/\S+)?", "", text, flags=re.IGNORECASE)
    return text.strip()


def _fetch_feed(url: str):
    import feedparser
    resp = requests.get(url, headers={"User-Agent": RSS_USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def fetch_candidates_rss(max_results: int = 20) -> list[Candidate]:
    min_words = int(os.getenv("MIN_WORDS", 120))
    max_words = int(os.getenv("MAX_WORDS", 850))
    subreddit_cfgs = _load_subreddit_config()
    candidates: list[Candidate] = []

    for cfg in subreddit_cfgs:
        name = cfg["name"]
        feed_urls = [
            f"https://www.reddit.com/r/{name}/top/.rss?t=week&limit=25",
            f"https://www.reddit.com/r/{name}/top/.rss?t=month&limit=15",
        ]
        for feed_url in feed_urls:
            try:
                feed = _fetch_feed(feed_url)
            except Exception as exc:
                logger.warning("No se pudo leer el feed RSS de r/%s (%s): %s", name, feed_url, exc)
                continue

            for rank, entry in enumerate(feed.entries):
                post_id = _extract_short_id(entry)
                if not post_id or is_post_used(post_id):
                    continue

                title = (getattr(entry, "title", "") or "").strip()
                raw_html = ""
                if getattr(entry, "content", None):
                    raw_html = entry.content[0].value
                else:
                    raw_html = getattr(entry, "summary", "")
                body = _clean_rss_body(raw_html)

                if body.strip() in REMOVED_MARKERS:
                    continue
                if _looks_like_repost_or_nsfw(title, body):
                    continue
                words = len((title + " " + body).split())
                if not (min_words <= words <= max_words):
                    continue

                # Rango sintético: cuanto antes aparece en "top de la semana/mes",
                # más prioridad le damos (no son upvotes reales).
                synthetic_score = max(1, 1000 - rank * 10)

                candidates.append(
                    Candidate(
                        post_id=post_id,
                        subreddit=name,
                        category=cfg.get("category", "story"),
                        title=title,
                        body=body,
                        score=synthetic_score,
                        permalink=getattr(entry, "link", f"https://reddit.com/r/{name}"),
                        score_is_estimated=True,
                    )
                )
            time.sleep(1.5)  # ritmo respetuoso entre peticiones, sin autenticación de por medio

    # Dedupe por si el mismo post aparece en top/week y top/month
    seen = set()
    deduped = []
    for c in sorted(candidates, key=lambda c: c.score, reverse=True):
        if c.post_id in seen:
            continue
        seen.add(c.post_id)
        deduped.append(c)
    return deduped[:max_results]


# ---------------------------------------------------------------------------
# MODO API (requiere app de Reddit aprobada)
# ---------------------------------------------------------------------------

def _reddit_client():
    import praw
    load_dotenv()
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "reddit-shorts-bot/1.0"),
        check_for_updates=False,
    )


def _passes_api_filters(submission, cfg: dict, min_words: int, max_words: int) -> bool:
    if submission.over_18 or getattr(submission, "spoiler", False):
        return False
    if not submission.is_self:
        return False
    flair = (submission.link_flair_text or "").strip()
    if flair in cfg.get("flair_blocklist", []):
        return False
    if submission.score < cfg.get("min_score", 500):
        return False
    body = (submission.selftext or "").strip()
    if body in REMOVED_MARKERS or submission.stickied:
        return False
    if REPOST_PATTERNS.search(submission.title) or REPOST_PATTERNS.search(body):
        return False
    words = len((submission.title + " " + body).split())
    return min_words <= words <= max_words


def fetch_candidates_api(limit_per_subreddit: int = 15, max_results: int = 20) -> list[Candidate]:
    min_words = int(os.getenv("MIN_WORDS", 120))
    max_words = int(os.getenv("MAX_WORDS", 850))
    reddit = _reddit_client()
    subreddit_cfgs = _load_subreddit_config()
    candidates: list[Candidate] = []

    for cfg in subreddit_cfgs:
        name = cfg["name"]
        try:
            sub = reddit.subreddit(name)
            posts = list(sub.hot(limit=limit_per_subreddit)) + \
                    list(sub.top(time_filter="week", limit=limit_per_subreddit))
        except Exception as exc:
            logger.warning("No se pudo leer r/%s: %s", name, exc)
            continue

        seen_ids = set()
        for submission in posts:
            if submission.id in seen_ids:
                continue
            seen_ids.add(submission.id)
            if is_post_used(submission.id) or not _passes_api_filters(submission, cfg, min_words, max_words):
                continue
            candidates.append(
                Candidate(
                    post_id=submission.id,
                    subreddit=name,
                    category=cfg.get("category", "story"),
                    title=submission.title.strip(),
                    body=(submission.selftext or "").strip(),
                    score=submission.score,
                    permalink=f"https://reddit.com{submission.permalink}",
                    score_is_estimated=False,
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:max_results]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def fetch_candidates(max_results: int = 20, **kwargs) -> list[Candidate]:
    mode = os.getenv("REDDIT_MODE", "rss").strip().lower()
    if mode == "api":
        return fetch_candidates_api(max_results=max_results, **kwargs)
    return fetch_candidates_rss(max_results=max_results)


if __name__ == "__main__":
    from state_db import init_db
    init_db()
    for c in fetch_candidates(max_results=5):
        tag = "~" if c.score_is_estimated else ""
        print(f"[{c.subreddit}] ({tag}{c.score}, {c.word_count} palabras) {c.title}")
