import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request

app = Flask(__name__)
PAGE_SIZE = 20
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/summaries.db"))


def safe_url(value: str) -> str | None:
    parsed = urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


@app.get("/")
def index() -> tuple[str, int] | str:
    query = request.args.get("q", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    pattern = f"%{query.replace('!', '!!').replace('%', '!%').replace('_', '!_')}%"
    try:
        uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            condition = "title LIKE ? ESCAPE '!' OR summary LIKE ? ESCAPE '!'"
            total = connection.execute(
                f"SELECT COUNT(*) FROM articles WHERE {condition}", (pattern, pattern)
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT title, url, summary, model, published_at, created_at FROM articles WHERE {condition} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (pattern, pattern, PAGE_SIZE, (page - 1) * PAGE_SIZE),
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read article database")
        return render_template("index.html", error=True, query=query, articles=[], page=page, total=0, page_size=PAGE_SIZE), 503

    articles = [{**dict(row), "safe_url": safe_url(row["url"])} for row in rows]
    return render_template("index.html", error=False, query=query, articles=articles, page=page, total=total, page_size=PAGE_SIZE)
