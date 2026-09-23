"""
state_db.py
-----------
Estado persistente en SQLite (un único archivo, sin servidor externo).
Evita repetir historias y lleva un registro de qué se subió y cuándo,
tanto para depurar como para respetar cuotas diarias por canal.
"""

from __future__ import annotations

import sqlite3
import datetime as dt
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "state" / "pipeline.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS used_posts (
    post_id TEXT PRIMARY KEY,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    score INTEGER,
    used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    lang TEXT NOT NULL,             -- 'en' | 'es'
    channel TEXT NOT NULL,          -- nombre/identificador del canal
    youtube_video_id TEXT,
    status TEXT NOT NULL,           -- 'pending' | 'uploaded' | 'failed'
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES used_posts (post_id)
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    videos_attempted INTEGER DEFAULT 0,
    videos_uploaded INTEGER DEFAULT 0,
    videos_failed INTEGER DEFAULT 0,
    notes TEXT
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def is_post_used(post_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM used_posts WHERE post_id = ?", (post_id,)
        ).fetchone()
        return row is not None


def mark_post_used(post_id: str, subreddit: str, title: str, category: str, score: int):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO used_posts
               (post_id, subreddit, title, category, score, used_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (post_id, subreddit, title, category, score, dt.datetime.utcnow().isoformat()),
        )


def record_upload(post_id: str, lang: str, channel: str, status: str,
                   youtube_video_id: str | None = None, error: str | None = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO uploads (post_id, lang, channel, youtube_video_id, status, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (post_id, lang, channel, youtube_video_id, status, error, dt.datetime.utcnow().isoformat()),
        )


def start_run() -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO run_log (started_at) VALUES (?)",
            (dt.datetime.utcnow().isoformat(),),
        )
        return cur.lastrowid


def finish_run(run_id: int, attempted: int, uploaded: int, failed: int, notes: str = ""):
    with get_conn() as conn:
        conn.execute(
            """UPDATE run_log SET finished_at=?, videos_attempted=?, videos_uploaded=?,
               videos_failed=?, notes=? WHERE id=?""",
            (dt.datetime.utcnow().isoformat(), attempted, uploaded, failed, notes, run_id),
        )


def uploads_today(channel: str) -> int:
    """Cuenta subidas con status='uploaded' en las últimas 24h para un canal (control de cuota diaria)."""
    since = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM uploads
               WHERE channel = ? AND status = 'uploaded' AND created_at >= ?""",
            (channel, since),
        ).fetchone()
        return row[0] if row else 0


if __name__ == "__main__":
    init_db()
    print(f"Base de datos inicializada en {DB_PATH}")
