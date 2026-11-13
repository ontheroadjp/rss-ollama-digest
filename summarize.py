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

# --- Default Configuration ---
RSS_URL = "https://news.yahoo.co.jp/rss/topics/top-picks.xml"  # Target site RSS feed URL
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3.5:4b"
MAX_TEXT_CHARS = 4000  # Balanced length for fast CPU prefill on T480s

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "summaries.db")
WEBHOOK_URL = ""


def log(msg):
    """Print timestamped message immediately without buffering."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def init_db(db_path):
    """Initialize SQLite database and create articles table if it does not exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            model TEXT NOT NULL,
            published_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def is_already_processed(conn, url):
    """Check if the article URL already exists in the database before fetching."""
    cur = conn.execute("SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,))
    return cur.fetchone() is not None


def save_article_to_db(conn, url, title, summary, model, published_at, overwrite=False):
    """Insert or update a single summarized article and commit immediately."""
    created_at = datetime.datetime.now().isoformat(timespec="seconds")
    if overwrite:
        conn.execute(
            """
            INSERT INTO articles (url, title, summary, model, published_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                model = excluded.model,
                published_at = excluded.published_at,
                created_at = excluded.created_at
            """,
            (url, title, summary, model, published_at, created_at),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO articles (url, title, summary, model, published_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, title, summary, model, published_at, created_at),
        )
    conn.commit()


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
        default=5,
        help="Maximum number of latest articles to process (default: 5)"
    )
    parser.add_argument(
        "--ignore-history",
        action="store_true",
        help="Ignore existing DB records and re-summarize latest articles (for testing)"
    )
    args = parser.parse_args()

    script_start = time.perf_counter()
    log(f"=== Process started (Max articles: {args.limit} | Model: {MODEL_NAME}) ===")
    log(f"[INFO] Database: {DB_PATH}")

    conn = init_db(DB_PATH)
    try:
        if args.ignore_history:
            log("[INFO] Test mode: Will overwrite existing records in DB.")

        log(f"1/4 Fetching RSS feed: {RSS_URL}")
        feed = feedparser.parse(RSS_URL)
        total_entries = len(feed.entries)
        log(f"-> RSS feed fetched (Total entries found: {total_entries})")

        if total_entries == 0:
            log("[WARN] No entries found. Please check RSS_URL.")
            return

        summaries_for_notify = []
        processed_count = 0

        for idx, entry in enumerate(feed.entries, start=1):
            if processed_count >= args.limit:
                log(f"[INFO] Reached limit ({args.limit} articles). Stopping loop.")
                break

            url = entry.get("link")
            title = entry.get("title", "Untitled")
            published_at = entry.get("published", "")

            if not url:
                continue

            # Pre-check in SQLite BEFORE downloading the article page
            if not args.ignore_history and is_already_processed(conn, url):
                log(f"[SKIP] Already in DB ({idx}/{total_entries}): {title}")
                continue

            current_num = processed_count + 1
            log(f"--- [{current_num}/{args.limit}] Processing: {title} ---")

            # Step 2: Download HTML
            log("2/4 Downloading article page...")
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                log("-> [FAILED] Could not download page. Skipping.")
                continue

            # Step 3: Extract main text
            log("3/4 Extracting main text...")
            body_text = trafilatura.extract(
                downloaded, include_comments=False, include_tables=False
            )
            if not body_text or len(body_text) < 200:
                char_len = len(body_text) if body_text else 0
                log(f"-> [SKIP] Text too short or extraction failed (Length: {char_len} chars).")
                continue

            target_len = min(len(body_text), MAX_TEXT_CHARS)
            log(f"-> Extraction complete (Total: {len(body_text)} chars -> Using first {target_len} chars)")

            # Step 4: Summarize with Ollama
            log(f"4/4 Generating summary with Ollama ({MODEL_NAME})...")
            article_start = time.perf_counter()
            try:
                summary = summarize_text(title, body_text)
                elapsed = time.perf_counter() - article_start
                log(f"-> Summary complete! (Elapsed: {elapsed:.1f}s)")

                save_article_to_db(
                    conn=conn,
                    url=url,
                    title=title,
                    summary=summary,
                    model=MODEL_NAME,
                    published_at=published_at,
                    overwrite=args.ignore_history,
                )
                log(f"-> Saved to SQLite (DB: {os.path.basename(DB_PATH)})")

                summaries_for_notify.append(f"## {title}\nURL: {url}\n\n{summary}\n\n---\n")
                processed_count += 1
            except Exception as e:
                if sys.stdout.isatty():
                    print()
                log(f"-> [ERROR] Ollama summarization failed ({url}): {e}")

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
    finally:
        conn.close()


if __name__ == "__main__":
    main()
