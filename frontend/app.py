import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import feedparser
import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for

from database import init_db
from scheduler import next_occurrence

app = Flask(__name__)
PAGE_SIZE = 20
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/summaries.db"))
MAX_FEED_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEZONE = "Asia/Tokyo"


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def display_timestamp(value: str | None, zone: ZoneInfo) -> str:
    if not value:
        return ""
    try:
        return parse_timestamp(value).astimezone(zone).strftime("%Y/%m/%d %H:%M:%S %Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return value


def configured_timezone(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT value FROM settings WHERE key = 'timezone'").fetchone()
    return row[0] if row else DEFAULT_TIMEZONE


def safe_url(value: str) -> str | None:
    parsed = urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


def publication_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return parse_timestamp(value).timestamp()
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
        selected_timezone = configured_timezone(connection)
        database_mb = DB_PATH.stat().st_size / 1_000_000
        settings = dict(connection.execute("SELECT key, value FROM settings"))
        history_rows = connection.execute("""SELECT created_at, 'event', message, NULL, NULL, NULL, NULL FROM schedule_events
            UNION ALL SELECT COALESCE(started_at, created_at), 'run', message, status, processed_count, finished_at, fetched_count FROM runs WHERE origin = 'automatic'
            ORDER BY 1 DESC LIMIT 100""").fetchall()
        zone = ZoneInfo(selected_timezone)
        history = [{"time": display_timestamp(row[0], zone), "kind": row[1], "message": row[2], "status": row[3], "count": row[4], "finished": display_timestamp(row[5], zone), "fetched": row[6]} for row in history_rows]
        last_run = connection.execute("SELECT MAX(finished_at) FROM runs WHERE status = 'completed'").fetchone()[0]
        last_updated = display_timestamp(last_run, ZoneInfo(selected_timezone)) if last_run else None
        next_update = display_timestamp(settings.get("schedule_next"), ZoneInfo(selected_timezone)) if settings.get("schedule_mode", "disabled") != "disabled" else None
    tab = "feeds" if request.args.get("tab") == "feeds" else "basic"
    return render_template("feeds.html", feeds=feeds, run=run, logs=logs, error=request.args.get("error"), tab=tab, selected_timezone=selected_timezone, timezones=sorted(available_timezones()), database_mb=database_mb, settings=settings, last_updated=last_updated, next_update=next_update, history=history)


@app.post("/settings/schedule")
def update_schedule():
    mode = request.form.get("mode", "")
    interval = request.form.get("interval", "").strip()
    daily_time = request.form.get("daily_time", "").strip()
    if mode not in ("disabled", "interval", "daily") or (mode == "interval" and (not interval.isascii() or not interval.isdecimal() or len(interval) > 5 or not 1 <= int(interval) <= 10080)):
        return redirect(url_for("feeds", error="取得間隔は 1〜10080 分で指定してください。"))
    try:
        if mode == "daily":
            datetime.strptime(daily_time, "%H:%M")
            if len(daily_time) != 5:
                raise ValueError("Invalid time")
    except ValueError:
        return redirect(url_for("feeds", error="有効な定時刻を指定してください。"))
    with init_db(DB_PATH) as connection:
        zone = configured_timezone(connection)
        values = {"schedule_mode": mode, "schedule_interval": interval if mode == "interval" else "60", "schedule_time": daily_time if mode == "daily" else "09:00"}
        if mode != "disabled":
            values["schedule_next"] = next_occurrence(mode, values["schedule_interval"], values["schedule_time"], zone, datetime.now(timezone.utc)).isoformat()
        connection.executemany("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", values.items())
        if mode == "disabled":
            message = "自動取得が無効に設定されました。"
        elif mode == "interval":
            message = f"自動取得が {interval} 分間隔に設定されました。"
        else:
            message = f"自動取得が毎日 {daily_time}（{zone}）に設定されました。"
        connection.execute("INSERT INTO schedule_events (message) VALUES (?)", (message,))
    return redirect(url_for("feeds"))


@app.post("/settings/timezone")
def update_timezone():
    selected_timezone = request.form.get("timezone", "")
    try:
        ZoneInfo(selected_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return redirect(url_for("feeds", tab="basic", error="有効なタイムゾーンを選択してください。"))
    with init_db(DB_PATH) as connection:
        connection.execute("INSERT INTO settings (key, value) VALUES ('timezone', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (selected_timezone,))
        settings = dict(connection.execute("SELECT key, value FROM settings"))
        if settings.get("schedule_mode") == "daily":
            next_run = next_occurrence("daily", "60", settings.get("schedule_time", "09:00"), selected_timezone, datetime.now(timezone.utc))
            connection.execute("UPDATE settings SET value = ? WHERE key = 'schedule_next'", (next_run.isoformat(),))
    return redirect(url_for("feeds", tab="basic"))


@app.post("/feeds")
def add_feed():
    url = request.form.get("url", "").strip()
    if not safe_url(url):
        return redirect(url_for("feeds", tab="feeds", error="HTTP または HTTPS の URL を入力してください。"))
    with init_db(DB_PATH) as connection:
        if connection.execute("SELECT 1 FROM feeds WHERE url = ?", (url,)).fetchone():
            return redirect(url_for("feeds", tab="feeds", error="この URL は登録済みです。"))
    try:
        title = fetch_feed_title(url)
    except (requests.RequestException, ValueError) as exc:
        logging.warning("Failed to retrieve RSS feed %s: %s", url, exc)
        return redirect(url_for("feeds", tab="feeds", error="フィードを取得または解析できません。URL とフィードを確認してください。"))
    try:
        with init_db(DB_PATH) as connection:
            connection.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", (url, title))
    except sqlite3.IntegrityError:
        return redirect(url_for("feeds", tab="feeds", error="この URL は登録済みです。"))
    return redirect(url_for("feeds", tab="feeds"))


@app.post("/feeds/<int:feed_id>/delete")
def delete_feed(feed_id: int):
    with init_db(DB_PATH) as connection:
        connection.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
    return redirect(url_for("feeds", tab="feeds"))


@app.post("/feeds/<int:feed_id>/settings")
def update_feed(feed_id: int):
    title = request.form.get("title", "").strip()
    raw_limit = request.form.get("article_limit", "").strip()
    if raw_limit and (not raw_limit.isascii() or not raw_limit.isdecimal() or not 1 <= int(raw_limit) <= 2147483647):
        return redirect(url_for("feeds", tab="feeds", error="取得数には 1 以上の整数を入力してください。"))
    limit = int(raw_limit) if raw_limit else None
    with init_db(DB_PATH) as connection:
        connection.execute("UPDATE feeds SET title = ?, article_limit = ? WHERE id = ?", (title, limit, feed_id))
    return redirect(url_for("feeds", tab="feeds"))


@app.post("/runs")
def start_run():
    try:
        with init_db(DB_PATH) as connection:
            cursor = connection.execute("INSERT INTO runs (status) VALUES ('queued')")
            run_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return redirect(url_for("feeds", tab="feeds", error="既に実行中です。"))
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "summarize.py"), "--run-id", str(run_id)],
            env={**os.environ, "DATABASE_PATH": str(DB_PATH)},
            start_new_session=True,
        )
    except OSError as exc:
        with init_db(DB_PATH) as connection:
            connection.execute("UPDATE runs SET status = 'failed', message = ? WHERE id = ?", (str(exc), run_id))
    return redirect(url_for("feeds", tab="feeds"))


@app.post("/runs/<int:run_id>/stop")
def stop_run(run_id: int):
    with init_db(DB_PATH) as connection:
        connection.execute("UPDATE runs SET status = 'stopping' WHERE id = ? AND status IN ('queued', 'running')", (run_id,))
    return redirect(url_for("feeds", tab="feeds"))


@app.get("/")
def index() -> tuple[str, int] | str:
    query = request.args.get("q", "").strip()
    feed_id = request.args.get("feed", "").strip()
    tag_id = request.args.get("tag", "").strip()
    status = request.args.get("status", "0")
    if status not in ("all", "0", "1", "2", "3"):
        status = "0"
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
            zone = ZoneInfo(configured_timezone(connection))
            available_feeds = connection.execute("SELECT id, url, title FROM feeds ORDER BY id").fetchall()
            condition = "(a.title LIKE ? ESCAPE '!' OR a.summary LIKE ? ESCAPE '!')"
            params: list[str | int] = [pattern, pattern]
            if feed_id:
                condition += " AND a.feed_url = (SELECT url FROM feeds WHERE CAST(id AS TEXT) = ?)"
                params.append(feed_id)
            if status != "all":
                condition += " AND a.is_read = ?"
                params.append(int(status))
            tags = connection.execute(
                f"""SELECT t.id, t.name, COUNT(*) AS count FROM tags t
                    JOIN article_tags at ON at.tag_id = t.id JOIN articles a ON a.id = at.article_id
                    WHERE {condition} GROUP BY t.id ORDER BY count DESC, t.name COLLATE NOCASE, t.id""", params
            ).fetchall()
            if tag_id:
                condition += " AND EXISTS (SELECT 1 FROM article_tags at WHERE at.article_id = a.id AND CAST(at.tag_id AS TEXT) = ?)"
                params.append(tag_id)
            total = connection.execute(
                f"SELECT COUNT(*) FROM articles a WHERE {condition}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT a.id, a.is_read, a.title, a.url, a.summary, a.model, a.published_at, a.created_at,
                           COALESCE(NULLIF(f.title, ''), a.feed_title, a.feed_url) AS source_title
                    FROM articles a LEFT JOIN feeds f ON f.url = a.feed_url
                    WHERE {condition}
                    ORDER BY publication_timestamp(a.published_at) DESC, a.created_at DESC, a.id DESC
                    LIMIT ? OFFSET ?""",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            ).fetchall()
            article_tags = {}
            for row in rows:
                article_tags[row['id']] = connection.execute(
                    "SELECT t.id, t.name FROM tags t JOIN article_tags at ON at.tag_id = t.id WHERE at.article_id = ? ORDER BY t.name", (row['id'],)
                ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read article database")
        return render_template("index.html", error=True, query=query, feed_id=feed_id, tag_id=tag_id, status=status, tags=[], feeds=[], articles=[], page=page, total=0, page_size=PAGE_SIZE), 503

    articles = [{**dict(row), "tags": article_tags[row["id"]], "safe_url": safe_url(row["url"]), "published_at": display_timestamp(row["published_at"], zone), "created_at": display_timestamp(row["created_at"], zone)} for row in rows]
    return render_template("index.html", error=False, query=query, feed_id=feed_id, tag_id=tag_id, status=status, tags=tags, feeds=available_feeds, articles=articles, page=page, total=total, page_size=PAGE_SIZE)


@app.post("/articles/<int:article_id>/read")
def update_read_status(article_id: int):
    status = request.form.get('is_read', '')
    if status not in ('1', '2', '3'):
        return jsonify(ok=False), 400
    with init_db(DB_PATH) as connection:
        cursor = connection.execute("UPDATE articles SET is_read = ? WHERE id = ?", (int(status), article_id))
    if request.headers.get('Accept') == 'application/json':
        return jsonify(ok=cursor.rowcount == 1), 200 if cursor.rowcount == 1 else 404
    return redirect(url_for('index', q=request.form.get('q', ''), feed=request.form.get('feed', ''), tag=request.form.get('tag', ''), status=request.form.get('status', '0'), page=request.form.get('page', 1)))
