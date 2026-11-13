"""Run scheduled RSS retrieval using the shared SQLite run lock."""

import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from database import init_db

POLL_SECONDS = 30
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/summaries.db"))


def next_occurrence(mode: str, interval: str, daily_time: str, zone: str, now: datetime) -> datetime:
    if mode == "interval":
        return now + timedelta(minutes=int(interval))
    local = now.astimezone(ZoneInfo(zone))
    hour, minute = map(int, daily_time.split(":"))
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
    if candidate.astimezone(timezone.utc) <= now:
        candidate = (candidate + timedelta(days=1)).replace(fold=0)
    return candidate.astimezone(timezone.utc)


def check_schedule(path: Path, now: datetime) -> int | None:
    with init_db(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        settings = dict(connection.execute("SELECT key, value FROM settings"))
        mode = settings.get("schedule_mode", "disabled")
        if mode == "disabled" or "schedule_next" not in settings or datetime.fromisoformat(settings["schedule_next"]) > now:
            return None
        try:
            run_id = connection.execute("INSERT INTO runs(status, origin) VALUES ('queued', 'automatic')").lastrowid
        except sqlite3.IntegrityError:
            return None
        next_run = next_occurrence(mode, settings.get("schedule_interval", "60"), settings.get("schedule_time", "09:00"), settings.get("timezone", "Asia/Tokyo"), now)
        connection.execute("UPDATE settings SET value = ? WHERE key = 'schedule_next'", (next_run.isoformat(),))
        return run_id


def main() -> None:
    while True:
        try:
            run_id = check_schedule(DB_PATH, datetime.now(timezone.utc))
            if run_id is not None:
                try:
                    subprocess.Popen([sys.executable, str(Path(__file__).with_name("summarize.py")), "--run-id", str(run_id)], env={**os.environ, "DATABASE_PATH": str(DB_PATH)}, start_new_session=True)
                except OSError as exc:
                    with init_db(DB_PATH) as connection:
                        connection.execute("UPDATE runs SET status = 'failed', message = ? WHERE id = ?", (str(exc), run_id))
                    logging.exception("Could not start scheduled retrieval")
        except (sqlite3.Error, ValueError, OSError):
            logging.exception("Could not check RSS schedule")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
