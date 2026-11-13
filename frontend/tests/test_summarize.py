import sqlite3
import sys
from types import SimpleNamespace

import summarize
from database import init_db


def test_existing_database_migrates_once(tmp_path):
    path = tmp_path / 'articles.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT)')
        connection.execute("INSERT INTO articles VALUES (1, 'https://example.com')")
    with init_db(path) as connection:
        assert connection.execute('SELECT url FROM articles').fetchone()[0] == 'https://example.com'
        assert connection.execute('SELECT COUNT(*) FROM feeds').fetchone()[0] == 0
    with init_db(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM feeds').fetchone()[0] == 0


def test_multiple_feeds_have_independent_limits(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute('DELETE FROM feeds')
        connection.executemany('INSERT INTO feeds(url) VALUES (?)', [('https://a.test/rss',), ('https://b.test/rss',)])
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(sys, 'argv', ['summarize.py', '-n', '1'])
    fetched = []
    def parse(url):
        fetched.append(url)
        return SimpleNamespace(feed={'title': 'Feed title'}, entries=[{'link': url + '/article', 'title': url}, {'link': url + '/second', 'title': url}], get=lambda key: False)
    monkeypatch.setattr(summarize.feedparser, 'parse', parse)
    monkeypatch.setattr(summarize.trafilatura, 'fetch_url', lambda url: 'html')
    monkeypatch.setattr(summarize.trafilatura, 'extract', lambda *args, **kwargs: 'x' * 201)
    monkeypatch.setattr(summarize, 'summarize_text', lambda title, body: 'summary')
    summarize.main()
    assert len(fetched) == 2
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 2
        assert connection.execute('SELECT url FROM articles ORDER BY url').fetchall() == [('https://a.test/rss/article',), ('https://b.test/rss/article',)]


def test_web_run_records_progress(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute("INSERT INTO feeds (url) VALUES ('https://example.com/rss')")
        run_id = connection.execute("INSERT INTO runs (status) VALUES ('queued')").lastrowid
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(sys, 'argv', ['summarize.py', '--run-id', str(run_id)])
    monkeypatch.setattr(summarize.feedparser, 'parse', lambda url: SimpleNamespace(feed={}, entries=[], get=lambda key: False))
    summarize.main()
    monkeypatch.setattr(summarize, 'RUN_ID', None)
    with sqlite3.connect(path) as connection:
        lines = [row[0] for row in connection.execute('SELECT line FROM run_logs WHERE run_id = ? ORDER BY id', (run_id,))]
        assert any('Fetching RSS feed' in line for line in lines)
        assert any('All tasks finished' in line for line in lines)
        assert connection.execute('SELECT status FROM runs WHERE id = ?', (run_id,)).fetchone()[0] == 'completed'


def test_default_has_no_article_limit(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute("INSERT INTO feeds (url) VALUES ('https://example.com/rss')")
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(sys, 'argv', ['summarize.py'])
    monkeypatch.setattr(summarize.feedparser, 'parse', lambda url: SimpleNamespace(
        feed={}, entries=[{'link': f'https://example.com/{i}', 'title': str(i)} for i in range(7)],
        get=lambda key: False,
    ))
    monkeypatch.setattr(summarize.trafilatura, 'fetch_url', lambda url: 'html')
    monkeypatch.setattr(summarize.trafilatura, 'extract', lambda *args, **kwargs: 'x' * 201)
    monkeypatch.setattr(summarize, 'summarize_text', lambda title, body: 'summary')
    summarize.main()
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 7


def test_configured_limits_and_cli_override(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute('DELETE FROM feeds')
        connection.executemany('INSERT INTO feeds(url, title, article_limit) VALUES (?, ?, ?)', [
            ('https://a.test', '', 1), ('https://b.test', 'Custom', 2),
        ])
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(summarize.feedparser, 'parse', lambda url: SimpleNamespace(
        feed={'title': 'Automatic'}, entries=[{'link': f'{url}/{i}', 'title': str(i)} for i in range(3)], get=lambda key: False,
    ))
    monkeypatch.setattr(summarize.trafilatura, 'fetch_url', lambda url: 'html')
    monkeypatch.setattr(summarize.trafilatura, 'extract', lambda *args, **kwargs: 'x' * 201)
    monkeypatch.setattr(summarize, 'summarize_text', lambda title, body: 'summary')
    monkeypatch.setattr(sys, 'argv', ['summarize.py'])
    summarize.main()
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 3
        assert connection.execute('SELECT title FROM feeds ORDER BY id').fetchall() == [('Automatic',), ('Custom',)]
        assert connection.execute("SELECT feed_title FROM articles WHERE url = 'https://a.test/0'").fetchone()[0] == 'Automatic'
        connection.execute('DELETE FROM articles')
    monkeypatch.setattr(sys, 'argv', ['summarize.py', '-n', '3'])
    summarize.main()
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 6


def test_existing_articles_are_linked_to_feed_without_resummarizing(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute("INSERT INTO feeds (url) VALUES ('https://example.com/rss')")
        connection.execute("INSERT INTO articles(url, title, summary, model, created_at) VALUES ('https://example.com/old', 'old', 'saved', 'model', '2026-01-01')")
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(sys, 'argv', ['summarize.py'])
    monkeypatch.setattr(summarize.feedparser, 'parse', lambda url: SimpleNamespace(
        feed={'title': 'Source'}, entries=[{'link': 'https://example.com/old', 'title': 'old'}], get=lambda key: False,
    ))
    summarize.main()
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT summary, feed_url, feed_title FROM articles').fetchone() == ('saved', 'https://example.com/rss', 'Source')
