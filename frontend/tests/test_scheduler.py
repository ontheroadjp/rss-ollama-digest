from datetime import datetime, timezone

from database import init_db
from scheduler import check_schedule, next_occurrence


def test_next_occurrence_uses_interval_and_local_time():
    now = datetime(2026, 11, 13, 0, tzinfo=timezone.utc)
    assert next_occurrence('interval', '60', '09:00', 'Asia/Tokyo', now).isoformat() == '2026-11-13T01:00:00+00:00'
    assert next_occurrence('daily', '60', '09:00', 'Asia/Tokyo', now).isoformat() == '2026-11-14T00:00:00+00:00'


def test_scheduler_claims_due_run_once_and_waits_for_active_run(tmp_path):
    path = tmp_path / 'db.sqlite'
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    with init_db(path) as connection:
        connection.executemany('INSERT INTO settings VALUES (?, ?)', [('schedule_mode', 'interval'), ('schedule_interval', '60'), ('schedule_next', '2026-11-12T23:00:00+00:00')])
        connection.execute("INSERT INTO runs(status) VALUES ('running')")
    assert check_schedule(path, now) is None
    with init_db(path) as connection:
        connection.execute("UPDATE runs SET status = 'completed'")
    assert check_schedule(path, now) is not None
    assert check_schedule(path, now) is None
    with init_db(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs WHERE status = 'queued'").fetchone()[0] == 1
        assert connection.execute("SELECT value FROM settings WHERE key = 'schedule_next'").fetchone()[0] == '2026-11-13T01:00:00+00:00'
