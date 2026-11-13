import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
from flask import Flask, redirect, render_template, request, url_for

from database import init_db

app = Flask(__name__)
PAGE_SIZE = 20
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/summaries.db"))
MAX_FEED_BYTES = 5 * 1024 * 1024


def safe_url(value: str) -> str | None:
    parsed = urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


def publication_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def fetch_feed_title(url: str) -> str:
    with requests.get(url, stream=True, timeout=(5, 15), headers={"User-Agent": "RSS Ollama Digest/1.0"}) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            data.extend(chunk)
            if len(data) > MAX_FEED_BYTES:
                raise ValueError("フィードのサイズが大きすぎます。")
    feed = feedparser.parse(bytes(data))
    if feed.bozo or not feed.version:
        raise ValueError("有効な RSS または Atom フィードではありません。")
    title = feed.feed.get("title", "").strip()
    if not title:
        raise ValueError("フィードにタイトルがありません。")
    return title


@app.get("/feeds")
def feeds() -> str:
    with init_db(DB_PATH) as connection:
        feeds = connection.execute("SELECT id, url, title, article_limit FROM feeds ORDER BY id").fetchall()
        run = connection.execute("SELECT id, status, message FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        logs = connection.execute("SELECT line FROM run_logs WHERE run_id = ? ORDER BY id", (run[0],)).fetchall() if run else []
    return render_template("feeds.html", feeds=feeds, run=run, logs=logs, error=request.args.get("error"))


@app.post("/feeds")
def add_feed():
    url = request.form.get("url", "").strip()
    if not safe_url(url):
        return redirect(url_for("feeds", error="HTTP または HTTPS の URL を入力してください。"))
    with init_db(DB_PATH) as connection:
        if connection.execute("SELECT 1 FROM feeds WHERE url = ?", (url,)).fetchone():
            return redirect(url_for("feeds", error="この URL は登録済みです。"))
    try:
        title = fetch_feed_title(url)
    except (requests.RequestException, ValueError) as exc:
        logging.warning("Failed to retrieve RSS feed %s: %s", url, exc)
        return redirect(url_for("feeds", error="フィードを取得または解析できません。URL とフィードを確認してください。"))
    try:
        with init_db(DB_PATH) as connection:
            connection.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", (url, title))
    except sqlite3.IntegrityError:
        return redirect(url_for("feeds", error="この URL は登録済みです。"))
    return redirect(url_for("feeds"))


@app.post("/feeds/<int:feed_id>/delete")
def delete_feed(feed_id: int):
    with init_db(DB_PATH) as connection:
        connection.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
    return redirect(url_for("feeds"))


@app.post("/feeds/<int:feed_id>/settings")
def update_feed(feed_id: int):
    title = request.form.get("title", "").strip()
    raw_limit = request.form.get("article_limit", "").strip()
    if raw_limit and (not raw_limit.isascii() or not raw_limit.isdecimal() or not 1 <= int(raw_limit) <= 2147483647):
        return redirect(url_for("feeds", error="取得数には 1 以上の整数を入力してください。"))
    limit = int(raw_limit) if raw_limit else None
    with init_db(DB_PATH) as connection:
        connection.execute("UPDATE feeds SET title = ?, article_limit = ? WHERE id = ?", (title, limit, feed_id))
    return redirect(url_for("feeds"))


@app.post("/runs")
def start_run():
    try:
        with init_db(DB_PATH) as connection:
            cursor = connection.execute("INSERT INTO runs (status) VALUES ('queued')")
            run_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return redirect(url_for("feeds", error="既に実行中です。"))
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "summarize.py"), "--run-id", str(run_id)],
            env={**os.environ, "DATABASE_PATH": str(DB_PATH)},
            start_new_session=True,
        )
    except OSError as exc:
        with init_db(DB_PATH) as connection:
            connection.execute("UPDATE runs SET status = 'failed', message = ? WHERE id = ?", (str(exc), run_id))
    return redirect(url_for("feeds"))


@app.get("/")
def index() -> tuple[str, int] | str:
    query = request.args.get("q", "").strip()
    feed_id = request.args.get("feed", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    pattern = f"%{query.replace('!', '!!').replace('%', '!%').replace('_', '!_')}%"
    try:
        if not DB_PATH.exists():
            raise sqlite3.OperationalError("Database does not exist")
        init_db(DB_PATH).close()
        uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.create_function("publication_timestamp", 1, publication_timestamp, deterministic=True)
            available_feeds = connection.execute("SELECT id, url, title FROM feeds ORDER BY id").fetchall()
            condition = "(a.title LIKE ? ESCAPE '!' OR a.summary LIKE ? ESCAPE '!')"
            params: list[str | int] = [pattern, pattern]
            if feed_id:
                condition += " AND a.feed_url = (SELECT url FROM feeds WHERE CAST(id AS TEXT) = ?)"
                params.append(feed_id)
            total = connection.execute(
                f"SELECT COUNT(*) FROM articles a WHERE {condition}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT a.title, a.url, a.summary, a.model, a.published_at, a.created_at,
                           COALESCE(NULLIF(f.title, ''), a.feed_title, a.feed_url) AS source_title
                    FROM articles a LEFT JOIN feeds f ON f.url = a.feed_url
                    WHERE {condition}
                    ORDER BY publication_timestamp(a.published_at) DESC, a.created_at DESC, a.id DESC
                    LIMIT ? OFFSET ?""",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read article database")
        return render_template("index.html", error=True, query=query, feed_id=feed_id, feeds=[], articles=[], page=page, total=0, page_size=PAGE_SIZE), 503

    articles = [{**dict(row), "safe_url": safe_url(row["url"])} for row in rows]
    return render_template("index.html", error=False, query=query, feed_id=feed_id, feeds=available_feeds, articles=articles, page=page, total=total, page_size=PAGE_SIZE)
