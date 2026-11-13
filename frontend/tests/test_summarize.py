import sqlite3
import sys
from types import SimpleNamespace

import summarize
import pytest
from database import init_db

real_generate_tags = summarize.generate_tags


@pytest.fixture(autouse=True)
def mock_tags(monkeypatch):
    monkeypatch.setattr(summarize, 'generate_tags', lambda title, summary: ['技術'])


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


def test_saved_article_has_utc_timestamp_and_preserves_publication_date(tmp_path):
    with init_db(tmp_path / 'articles.db') as connection:
        published = 'Fri, 13 Nov 2026 08:40:24 GMT'
        summarize.save_article_to_db(connection, 'article', 'Title', 'Summary', 'model', published, 'feed', 'Feed')
        saved, created = connection.execute('SELECT published_at, created_at FROM articles').fetchone()
        assert saved == published
        assert created.endswith('+00:00')


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


def test_body_guid_tags_and_guid_lookup(tmp_path):
    with init_db(tmp_path / 'articles.db') as connection:
        summarize.save_article_to_db(connection, 'url', 'Title', 'Summary', 'model', '', 'feed', 'Feed', body='全文', guid='guid', tags=['技術'])
        assert connection.execute('SELECT body, guid FROM articles').fetchone() == ('全文', 'guid')
        assert connection.execute('SELECT name FROM tags JOIN article_tags ON tags.id = article_tags.tag_id').fetchall() == [('技術',)]
        assert summarize.is_already_processed(connection, 'changed-url', 'feed', 'guid')
        assert not summarize.is_already_processed(connection, 'changed-url', 'other-feed', 'guid')
        connection.execute('UPDATE articles SET is_read = 1')
        summarize.save_article_to_db(connection, 'url', 'Title', 'Summary', 'model', '', 'feed', 'Feed', overwrite=True, tags=['新タグ'])
        assert connection.execute('SELECT is_read FROM articles').fetchone() == (1,)
        assert connection.execute('SELECT name FROM tags JOIN article_tags ON tags.id = article_tags.tag_id').fetchall() == [('新タグ',)]


def test_stop_requested_before_worker_starts(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute("INSERT INTO feeds(url) VALUES ('feed')")
        run_id = connection.execute("INSERT INTO runs(status) VALUES ('stopping')").lastrowid
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(sys, 'argv', ['summarize.py', '--run-id', str(run_id)])
    monkeypatch.setattr(summarize.feedparser, 'parse', lambda url: pytest.fail('stopped run fetched feed'))
    summarize.main()
    monkeypatch.setattr(summarize, 'RUN_ID', None)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT status FROM runs').fetchone()[0] == 'stopped'


def test_tags_are_deduplicated_and_limited(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {'response': '{"tags": ["技術", "技術", "AI", "科学", "経済"]}'}

    monkeypatch.setattr(summarize.requests, 'post', lambda *args, **kwargs: Response())
    assert real_generate_tags('title', 'summary') == ['技術', 'AI', '科学']


def test_stop_during_summary_leaves_article_for_next_run(tmp_path, monkeypatch):
    path = tmp_path / 'articles.db'
    with init_db(path) as connection:
        connection.execute("INSERT INTO feeds(url) VALUES ('feed')")
        run_id = connection.execute("INSERT INTO runs(status) VALUES ('queued')").lastrowid
    monkeypatch.setattr(summarize, 'DB_PATH', str(path))
    monkeypatch.setattr(sys, 'argv', ['summarize.py', '--run-id', str(run_id)])
    monkeypatch.setattr(summarize.feedparser, 'parse', lambda url: SimpleNamespace(feed={}, entries=[{'link': 'article'}], get=lambda key: False))
    monkeypatch.setattr(summarize.trafilatura, 'fetch_url', lambda url: 'html')
    monkeypatch.setattr(summarize.trafilatura, 'extract', lambda *args, **kwargs: 'x' * 201)

    def stop_during_summary(title, body):
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE runs SET status = 'stopping' WHERE id = ?", (run_id,))
        return 'summary'

    monkeypatch.setattr(summarize, 'summarize_text', stop_during_summary)
    summarize.main()
    monkeypatch.setattr(summarize, 'RUN_ID', None)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM articles').fetchone()[0] == 0
        assert connection.execute('SELECT status FROM runs').fetchone()[0] == 'stopped'
