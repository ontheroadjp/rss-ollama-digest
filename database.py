"""Shared SQLite initialization for the summarizer and the web interface."""

import sqlite3
import json
from pathlib import Path

def init_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL, summary TEXT NOT NULL, model TEXT NOT NULL,
        published_at TEXT, created_at TEXT NOT NULL)""")
    conn.execute("BEGIN IMMEDIATE")
    article_columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    if "feed_url" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN feed_url TEXT")
    if "feed_title" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN feed_title TEXT")
    for column in ("body", "guid"):
        if column not in article_columns:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {column} TEXT")
    if "is_read" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS article_tags (article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, tag_id INTEGER NOT NULL REFERENCES tags(id), PRIMARY KEY (article_id, tag_id))")
    if "tags" in article_columns:
        for article_id, raw_tags in conn.execute("SELECT id, tags FROM articles WHERE tags IS NOT NULL").fetchall():
            tags = json.loads(raw_tags)
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise ValueError(f"Invalid tags for article {article_id}")
            for tag in tags:
                conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
                conn.execute("INSERT OR IGNORE INTO article_tags (article_id, tag_id) SELECT ?, id FROM tags WHERE name = ?", (article_id, tag))
        conn.execute("ALTER TABLE articles DROP COLUMN tags")
    conn.execute("CREATE TABLE IF NOT EXISTS feeds (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(feeds)")}
    if "title" not in columns:
        conn.execute("ALTER TABLE feeds ADD COLUMN title TEXT NOT NULL DEFAULT ''")
    if "article_limit" not in columns:
        conn.execute("ALTER TABLE feeds ADD COLUMN article_limit INTEGER CHECK (article_limit IS NULL OR article_limit > 0)")
    conn.execute("""CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY, status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("DROP INDEX IF EXISTS one_active_run")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_v2 ON runs ((1)) WHERE status IN ('queued', 'running', 'stopping')")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_logs (
        id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, line TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES runs(id))""")
    conn.commit()
    return conn
