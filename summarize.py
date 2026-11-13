import argparse
import datetime
import json
import os
import sqlite3
import sys
import threading
import time
import feedparser
import requests
import trafilatura

from database import init_db

# --- Default Configuration ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = "qwen3.5:4b"
MAX_TEXT_CHARS = 4000  # Balanced length for fast CPU prefill on T480s

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "summaries.db"))
WEBHOOK_URL = ""
RUN_ID: int | None = None


def log(msg):
    """Print timestamped message immediately without buffering."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {msg}"
    print(line, flush=True)
    if RUN_ID is not None:
        try:
            with sqlite3.connect(DB_PATH, timeout=30) as connection:
                connection.execute("INSERT INTO run_logs (run_id, line) VALUES (?, ?)", (RUN_ID, line))
        except sqlite3.Error as exc:
            print(f"[WARN] Could not save progress: {exc}", file=sys.stderr, flush=True)


def is_already_processed(conn, url, feed_url=None, guid=None):
    """Check if the article URL already exists in the database before fetching."""
    cur = conn.execute("SELECT 1 FROM articles WHERE url = ? OR (? IS NOT NULL AND feed_url = ? AND guid = ?) LIMIT 1", (url, guid, feed_url, guid))
    return cur.fetchone() is not None


def save_article_to_db(conn, url, title, summary, model, published_at, feed_url, feed_title, overwrite=False, body=None, guid=None, tags=None):
    """Insert or update a single summarized article and commit immediately."""
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if overwrite:
        conn.execute(
            """
            INSERT INTO articles (url, title, summary, model, published_at, created_at, feed_url, feed_title, body, guid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                model = excluded.model,
                published_at = excluded.published_at,
                created_at = excluded.created_at,
                feed_url = excluded.feed_url,
                feed_title = excluded.feed_title,
                body = excluded.body, guid = excluded.guid
            """,
            (url, title, summary, model, published_at, created_at, feed_url, feed_title, body, guid),
        )
    else:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO articles (url, title, summary, model, published_at, created_at, feed_url, feed_title, body, guid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (url, title, summary, model, published_at, created_at, feed_url, feed_title, body, guid),
        )
        if cursor.rowcount == 0:
            conn.commit()
            return
    article_id = conn.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()[0]
    conn.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))
    for tag in tags or []:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        conn.execute("INSERT OR IGNORE INTO article_tags (article_id, tag_id) SELECT ?, id FROM tags WHERE name = ?", (article_id, tag))
    conn.commit()


def generate_tags(title: str, summary: str) -> list[str]:
    schema = {"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3}}, "required": ["tags"]}
    payload = {"model": MODEL_NAME, "prompt": f"記事に合う簡潔な日本語タグを1〜3個生成してください。JSON形式: {{\"tags\": [\"タグ\"]}}\nタイトル: {title}\n要約: {summary}", "stream": False, "format": schema, "think": False, "options": {"num_ctx": 4096, "num_thread": 4}}
    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    response.raise_for_status()
    result = json.loads(response.json()["response"])
    tags = result.get("tags", []) if isinstance(result, dict) else []
    if not isinstance(tags, list):
        raise ValueError("Invalid tags response")
    cleaned = list(dict.fromkeys(tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()))[:3]
    if not cleaned:
        raise ValueError("No tags generated")
    return cleaned


def stop_requested(conn: sqlite3.Connection) -> bool:
    return RUN_ID is not None and conn.execute("SELECT status FROM runs WHERE id = ?", (RUN_ID,)).fetchone()[0] == "stopping"


def summarize_text(title, text):
    truncated_text = text[:MAX_TEXT_CHARS]
    prompt = f"""以下のWeb記事の本文を読み、重要なポイントを日本語で簡潔に要約してください。

【出力形式】
- 3行の箇条書きで要点をまとめる
- 最後に1行で全体の結論を書く

【記事タイトル】
{title}

【記事本文】
{truncated_text}
"""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": True,
        "think": False,  # Disable Qwen3.5 internal thinking for much faster summary
        "keep_alive": "1m",
        "options": {
            "num_ctx": 4096,
            "num_thread": 4,
            "temperature": 0.3,
        },
    }

    start_time = time.perf_counter()
    is_tty = sys.stdout.isatty()
    spinner = ["|", "/", "-", "\\"]
    estimated_max_tokens = 220
    bar_width = 20

    full_response = []
    state = {"tokens": 0, "done": False}
    lock = threading.Lock()

    def render_progress():
        tick = 0
        while True:
            with lock:
                if state["done"]:
                    break
                tokens = state["tokens"]
            elapsed = time.perf_counter() - start_time
            spin = spinner[tick % len(spinner)]
            if tokens == 0:
                line_str = f"  {spin} [--------------------]   0% | Reading prompt... | {elapsed:.1f}s"
            else:
                ratio = min(tokens / estimated_max_tokens, 0.99)
                filled = int(bar_width * ratio)
                bar = "#" * filled + "-" * (bar_width - filled)
                percent = int(ratio * 100)
                line_str = f"  {spin} [{bar}] {percent:3d}% | {tokens} tokens | {elapsed:.1f}s"
            sys.stdout.write(f"\r{line_str:<70}")
            sys.stdout.flush()
            tick += 1
            time.sleep(0.2)

    monitor_thread = None
    if is_tty:
        monitor_thread = threading.Thread(target=render_progress, daemon=True)
        monitor_thread.start()

    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=300) as res:
            res.raise_for_status()
            last_progress = time.perf_counter()
            for line in res.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                token_text = chunk.get("response", "")
                thinking_text = chunk.get("thinking", "")
                if token_text or thinking_text:
                    if token_text:
                        full_response.append(token_text)
                    with lock:
                        state["tokens"] += 1
                    if RUN_ID is not None and time.perf_counter() - last_progress >= 5:
                        log(f"  Generating summary: {state['tokens']} tokens ({time.perf_counter() - start_time:.1f}s)")
                        last_progress = time.perf_counter()

                if chunk.get("done"):
                    break
    finally:
        with lock:
            state["done"] = True
        if monitor_thread:
            monitor_thread.join()
        if is_tty:
            elapsed = time.perf_counter() - start_time
            bar = "#" * bar_width
            done_str = f"  * [{bar}] 100% | {state['tokens']} tokens | {elapsed:.1f}s"
            sys.stdout.write(f"\r{done_str:<70}\n")
            sys.stdout.flush()

    return "".join(full_response).strip()


def send_notification(message):
    if not WEBHOOK_URL:
        return
    payload = {"text": message, "content": message}
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        log(f"[ERROR] Failed to send notification: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch RSS articles, summarize them with a local LLM, and store in SQLite."
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="Override the configured maximum number of articles per feed"
    )
    parser.add_argument(
        "--ignore-history",
        action="store_true",
        help="Ignore existing DB records and re-summarize latest articles (for testing)"
    )
    parser.add_argument("--run-id", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    global RUN_ID
    RUN_ID = args.run_id

    script_start = time.perf_counter()
    limit_label = str(args.limit) if args.limit is not None else "feed settings"
    log(f"=== Process started (Max articles per feed: {limit_label} | Model: {MODEL_NAME}) ===")
    log(f"[INFO] Database: {DB_PATH}")

    conn = init_db(DB_PATH)
    try:
        if args.run_id is not None:
            conn.execute("UPDATE runs SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'queued'", (args.run_id,))
            conn.commit()
        if args.ignore_history:
            log("[INFO] Test mode: Will overwrite existing records in DB.")

        feeds = conn.execute("SELECT id, url, title, article_limit FROM feeds ORDER BY id").fetchall()
        entries = []
        errors = []
        for feed_id, feed_url, title, configured_limit in feeds:
            if stop_requested(conn):
                break
            log(f"1/4 Fetching RSS feed: {feed_url}")
            feed = feedparser.parse(feed_url)
            feed_title = feed.feed.get("title", "").strip()
            if not title and feed_title:
                conn.execute("UPDATE feeds SET title = ? WHERE id = ? AND title = ''", (feed_title, feed_id))
                conn.commit()
            if feed.get("bozo"):
                log(f"[WARN] Feed could not be parsed: {feed_url}: {feed.get('bozo_exception')}")
                errors.append(f"フィードの取得に失敗しました: {feed_url}")
            feed_limit = args.limit if args.limit is not None else configured_limit
            entries.extend((feed_url, title or feed_title or feed_url, feed_limit, entry) for entry in feed.entries)
        total_entries = len(entries)
        log(f"-> RSS feeds fetched (Total entries found: {total_entries})")

        summaries_for_notify = []
        processed_count = 0
        feed_counts: dict[str, int] = {}
        limited_feeds: set[str] = set()

        for idx, (feed_url, feed_title, feed_limit, entry) in enumerate(entries, start=1):
            if stop_requested(conn):
                break
            url = entry.get("link")
            guid = entry.get("id") or None
            if url:
                conn.execute("UPDATE articles SET feed_url = ?, feed_title = ? WHERE url = ? AND feed_url IS NULL", (feed_url, feed_title, url))
                conn.commit()
            if feed_limit is not None and feed_counts.get(feed_url, 0) >= feed_limit:
                if feed_url not in limited_feeds:
                    log(f"[INFO] Reached limit ({feed_limit} articles) for {feed_url}.")
                    limited_feeds.add(feed_url)
                continue

            title = entry.get("title", "Untitled")
            published_at = entry.get("published", "")

            if not url:
                continue

            # Pre-check in SQLite BEFORE downloading the article page
            if not args.ignore_history and is_already_processed(conn, url, feed_url, guid):
                log(f"[SKIP] Already in DB ({idx}/{total_entries}): {title}")
                continue

            current_num = feed_counts.get(feed_url, 0) + 1
            limit_label = str(feed_limit) if feed_limit is not None else "unlimited"
            log(f"--- [{current_num}/{limit_label}] Feed: {feed_url} | Processing: {title} ---")

            # Step 2: Download HTML
            log("2/4 Downloading article page...")
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                log("-> [FAILED] Could not download page. Skipping.")
                continue
            if stop_requested(conn):
                break

            # Step 3: Extract main text
            log("3/4 Extracting main text...")
            body_text = trafilatura.extract(
                downloaded, include_comments=False, include_tables=True
            )
            if not body_text or len(body_text) < 200:
                char_len = len(body_text) if body_text else 0
                log(f"-> [SKIP] Text too short or extraction failed (Length: {char_len} chars).")
                continue
            if stop_requested(conn):
                break

            target_len = min(len(body_text), MAX_TEXT_CHARS)
            log(f"-> Extraction complete (Total: {len(body_text)} chars -> Using first {target_len} chars)")

            # Step 4: Summarize with Ollama
            log(f"4/4 Generating summary with Ollama ({MODEL_NAME})...")
            article_start = time.perf_counter()
            try:
                summary = summarize_text(title, body_text)
                if stop_requested(conn):
                    break
                tags = generate_tags(title, summary)
                elapsed = time.perf_counter() - article_start
                log(f"-> Summary complete! (Elapsed: {elapsed:.1f}s)")

                save_article_to_db(
                    conn=conn,
                    url=url,
                    title=title,
                    summary=summary,
                    model=MODEL_NAME,
                    published_at=published_at,
                    feed_url=feed_url,
                    feed_title=feed_title,
                    overwrite=args.ignore_history,
                    body=body_text, guid=guid, tags=tags,
                )
                log(f"-> Saved to SQLite (DB: {os.path.basename(DB_PATH)})")

                summaries_for_notify.append(f"## {title}\nURL: {url}\n\n{summary}\n\n---\n")
                processed_count += 1
                feed_counts[feed_url] = current_num
            except Exception as e:
                if sys.stdout.isatty():
                    print()
                log(f"-> [ERROR] Ollama summarization failed ({url}): {e}")
                errors.append(f"要約に失敗しました: {url}: {e}")

        if summaries_for_notify:
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            send_notification(
                f"**{today_str} New Article Summaries ({processed_count})**\n\n"
                + "\n".join(summaries_for_notify)
            )
        else:
            log("No new articles were summarized.")

        total_elapsed = time.perf_counter() - script_start
        log(f"=== All tasks finished (Processed: {processed_count} | Total time: {total_elapsed:.1f}s) ===")
        if args.run_id is not None:
            status = "stopped" if stop_requested(conn) else ("failed" if errors else "completed")
            message = f"{processed_count} 件の記事を要約しました。" + " ".join(errors)
            conn.execute("UPDATE runs SET status = CASE WHEN status = 'stopping' THEN 'stopped' ELSE ? END, message = ?, processed_count = ?, fetched_count = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?", (status, message, processed_count, total_entries, args.run_id))
            conn.commit()
    except Exception as exc:
        if args.run_id is not None:
            conn.execute("UPDATE runs SET status = 'failed', message = ? WHERE id = ?", (str(exc), args.run_id))
            conn.commit()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
