import sqlite3

import pytest

import app as browser


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "summaries.db"
    monkeypatch.setattr(browser, "DB_PATH", database)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT, title TEXT, summary TEXT, model TEXT, published_at TEXT, created_at TEXT)")
        connection.executemany(
            "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(i, "https://example.com/" + str(i), "記事 " + str(i), "要約 100%", "model", None, f"2026-01-{i:02}") for i in range(1, 23)],
        )
    return browser.app.test_client()


def test_search_pagination_and_escaping(client):
    first = client.get("/?q=100%25")
    assert first.status_code == 200
    assert "22 件の記事" in first.text
    assert "次へ" in first.text
    assert "記事 22" in first.text
    second = client.get("/?q=100%25&page=2")
    assert "記事 1" in second.text
    assert "前へ" in second.text
    assert "0 件の記事" in client.get("/?q=missing").text


def test_run_stop_control_and_database_size(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        run_id = connection.execute("INSERT INTO runs(status) VALUES ('running')").lastrowid
    page = client.get('/feeds')
    assert 'class="stop-button"' in page.text
    assert '中止' in page.text
    assert 'DB容量:' in client.get('/feeds?tab=basic').text
    client.post(f'/runs/{run_id}/stop')
    with sqlite3.connect(browser.DB_PATH) as connection:
        assert connection.execute('SELECT status FROM runs WHERE id = ?', (run_id,)).fetchone()[0] == 'stopping'
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO runs(status) VALUES ('queued')")


def test_missing_database_is_not_created(tmp_path, monkeypatch):
    path = tmp_path / "missing.db"
    monkeypatch.setattr(browser, "DB_PATH", path)
    response = browser.app.test_client().get("/")
    assert response.status_code == 503
    assert not path.exists()


def test_unsafe_links_are_not_rendered(client, monkeypatch):
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("UPDATE articles SET url = 'javascript:alert(1)' WHERE id = 22")
    assert 'href="javascript:' not in client.get("/").text


def test_feed_registration_deletion_and_validation(client, monkeypatch):
    assert '管理画面' in client.get('/').text
    assert 'フィードは登録されていません' in client.get('/feeds').text
    assert '入力してください' in client.post('/feeds', data={'url': 'file:///etc/passwd'}, follow_redirects=True).text
    monkeypatch.setattr(browser.requests, 'get', lambda *args, **kwargs: FakeResponse(b'<?xml version="1.0"?><rss version="2.0"><channel><title>Example feed</title><link>https://example.com</link><description>News</description></channel></rss>'))
    url = 'https://example.com/rss'
    registered = client.post('/feeds', data={'url': url}, follow_redirects=True).text
    assert url in registered
    assert 'Example feed' in registered
    assert '登録済み' in client.post('/feeds', data={'url': url}, follow_redirects=True).text
    with sqlite3.connect(browser.DB_PATH) as connection:
        feed_id = connection.execute('SELECT id FROM feeds WHERE url = ?', (url,)).fetchone()[0]
    assert url not in client.post(f'/feeds/{feed_id}/delete', follow_redirects=True).text


class FakeResponse:
    def __init__(self, body, status_error=None):
        self.body = body
        self.status_error = status_error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def iter_content(self, chunk_size):
        yield self.body


@pytest.mark.parametrize('response', [
    FakeResponse(b'<html><title>Not a feed</title></html>'),
    FakeResponse(b'<rss><broken>'),
    FakeResponse(b'', browser.requests.HTTPError('404')),
    FakeResponse(b'<rss version="2.0"><channel></channel></rss>'),
])
def test_feed_registration_rejects_invalid_responses(client, monkeypatch, response):
    monkeypatch.setattr(browser.requests, 'get', lambda *args, **kwargs: response)
    result = client.post('/feeds', data={'url': 'https://example.com/bad'}, follow_redirects=True)
    assert 'フィードを取得または解析できません' in result.text
    with sqlite3.connect(browser.DB_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM feeds WHERE url = 'https://example.com/bad'").fetchone()[0] == 0


def test_feed_registration_rejects_connection_error(client, monkeypatch):
    def fail(*args, **kwargs):
        raise browser.requests.Timeout('timeout')
    monkeypatch.setattr(browser.requests, 'get', fail)
    assert 'フィードを取得または解析できません' in client.post('/feeds', data={'url': 'https://example.com/timeout'}, follow_redirects=True).text


def test_run_prevents_duplicate_and_reports_start_failure(client, monkeypatch):
    calls = []
    monkeypatch.setattr(browser.subprocess, 'Popen', lambda *args, **kwargs: calls.append(args))
    assert '開始待ち' in client.post('/runs', follow_redirects=True).text
    assert '既に実行中' in client.post('/runs', follow_redirects=True).text
    assert len(calls) == 1

    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("UPDATE runs SET status = 'completed'")
    def fail(*args, **kwargs):
        raise OSError('cannot start')
    monkeypatch.setattr(browser.subprocess, 'Popen', fail)
    assert 'cannot start' in client.post('/runs', follow_redirects=True).text


def test_deleted_feed_is_not_recreated(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("INSERT INTO feeds (url) VALUES ('https://example.com/rss')")
        connection.execute('DELETE FROM feeds')
    assert 'フィードは登録されていません' in client.get('/feeds').text


def test_run_progress_is_escaped_and_displayed(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        run_id = connection.execute("INSERT INTO runs (status) VALUES ('running')").lastrowid
        connection.execute('INSERT INTO run_logs (run_id, line) VALUES (?, ?)', (run_id, '<script>progress</script>'))
    response = client.get('/feeds')
    assert '実行ログ' in response.text
    assert '&lt;script&gt;progress&lt;/script&gt;' in response.text
    assert 'http-equiv="refresh"' not in response.text
    assert 'data-active="true"' in response.text
    assert 'log.scrollTop = log.scrollHeight' in response.text


def test_feed_settings_and_validation(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("INSERT INTO feeds (url) VALUES ('https://example.com/rss')")
        feed_id = connection.execute('SELECT id FROM feeds').fetchone()[0]
    path = f'/feeds/{feed_id}/settings'
    response = client.post(path, data={'title': 'ニュース', 'article_limit': '3'}, follow_redirects=True)
    assert 'ニュース' in response.text
    with sqlite3.connect(browser.DB_PATH) as connection:
        assert connection.execute('SELECT title, article_limit FROM feeds').fetchone() == ('ニュース', 3)
    assert '整数を入力' in client.post(path, data={'article_limit': '-1'}, follow_redirects=True).text
    client.post(path, data={'title': '', 'article_limit': ''})
    with sqlite3.connect(browser.DB_PATH) as connection:
        assert connection.execute('SELECT title, article_limit FROM feeds').fetchone() == ('', None)


def test_article_order_uses_publication_time_and_shows_feed(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("INSERT INTO feeds (url, title) VALUES ('https://example.com/rss', 'Feed & News')")
        feed_url = connection.execute('SELECT url FROM feeds').fetchone()[0]
        connection.execute("UPDATE articles SET published_at = 'Fri, 13 Nov 2026 04:00:00 GMT', feed_url = ? WHERE id = 1", (feed_url,))
        connection.execute("UPDATE articles SET published_at = '2026-11-13T15:00:00+09:00' WHERE id = 2")
        connection.execute("UPDATE articles SET published_at = 'invalid date' WHERE id = 22")
    text = client.get('/').text
    assert text.index('記事 2 ↗') < text.index('記事 1 ↗') < text.index('記事 22 ↗')
    assert 'Feed &amp; News' in text
    assert '2026/11/13 13:00:00 JST' in text
    assert 'invalid date' in text


def test_timezone_setting_changes_display_without_changing_stored_rss_date(client):
    basic = client.get('/feeds?tab=basic').text
    assert '基本設定' in basic
    assert 'value="Asia/Tokyo" selected' in basic
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("UPDATE articles SET published_at = 'Fri, 13 Nov 2026 08:40:24 GMT' WHERE id = 22")
    assert '2026/11/13 17:40:24 JST' in client.get('/').text
    client.post('/settings/timezone', data={'timezone': 'America/New_York'})
    assert '2026/11/13 03:40:24 EST' in client.get('/').text
    assert 'value="America/New_York" selected' in client.get('/feeds?tab=basic').text
    assert '有効なタイムゾーン' in client.post('/settings/timezone', data={'timezone': '../invalid'}, follow_redirects=True).text
    with sqlite3.connect(browser.DB_PATH) as connection:
        assert connection.execute('SELECT published_at FROM articles WHERE id = 22').fetchone()[0] == 'Fri, 13 Nov 2026 08:40:24 GMT'
        assert connection.execute("SELECT value FROM settings WHERE key = 'timezone'").fetchone()[0] == 'America/New_York'


def test_feed_name_falls_back_after_deletion(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("UPDATE articles SET feed_url = 'https://deleted.test/rss', feed_title = '旧フィード' WHERE id = 22")
    assert '旧フィード' in client.get('/').text


def test_filter_by_feed_combines_with_search_and_pagination(client):
    client.get('/feeds')
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute("INSERT INTO feeds (url) VALUES ('https://example.com/rss')")
        feed_id, feed_url = connection.execute('SELECT id, url FROM feeds').fetchone()
        connection.execute("UPDATE feeds SET title = '主要ニュース'")
        connection.execute('UPDATE articles SET feed_url = ? WHERE id <= 21', (feed_url,))
    page = client.get(f'/?feed={feed_id}&q=100%25')
    assert '21 件の記事' in page.text
    assert '記事 22 ↗' not in page.text
    assert f'value="{feed_id}" selected' in page.text
    assert f'feed={feed_id}' in page.text
    assert '記事 1 ↗' in client.get(f'/?feed={feed_id}&q=100%25&page=2').text
    assert '0 件の記事' in client.get(f'/?feed={feed_id}&q=missing').text
    assert '22 件の記事' in client.get('/').text


def test_read_status_and_tag_filter(client):
    client.get('/')
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.executemany('INSERT INTO tags(name) VALUES (?)', [('頻出',), ('少数',)])
        connection.executemany('INSERT INTO article_tags VALUES (?, ?)', [(22, 1), (21, 1), (22, 2)])
    page = client.get('/').text
    assert page.index('頻出 (2)') < page.index('少数 (1)')
    assert '>興味あり</button>' in page
    assert '>興味なし</button>' in page
    assert '>既読</button>' in page
    assert '>未読</option>' in page
    assert "fetch(form.action" in page
    assert 'setTimeout(updateResults, 350)' in page
    assert "if (tag) tag.remove()" in page
    assert '2 件の記事' in client.get('/?tag=1').text
    client.post('/articles/22/read', data={'is_read': '1'})
    assert '記事 22 ↗' not in client.get('/').text
    read_page = client.get('/?status=all&tag=1').text
    assert '記事 22 ↗' in read_page
    assert 'aria-pressed="true">興味なし</button>' in read_page
    assert client.post('/articles/22/read', data={'is_read': '2'}, headers={'Accept': 'application/json'}).json == {'ok': True}
    assert '記事 22 ↗' in client.get('/?status=2').text
    assert '記事 22 ↗' not in client.get('/?status=1').text
    assert client.post('/articles/22/read', data={'is_read': '3'}, headers={'Accept': 'application/json'}).json == {'ok': True}
    assert '記事 22 ↗' in client.get('/?status=3').text
    assert '記事 22 ↗' not in client.get('/?status=2').text
    assert client.post('/articles/22/read', data={'is_read': '0'}, headers={'Accept': 'application/json'}).status_code == 400
    assert client.post('/articles/999/read', data={'is_read': '1'}, headers={'Accept': 'application/json'}).status_code == 404


def test_legacy_tags_migrate_once(client):
    with sqlite3.connect(browser.DB_PATH) as connection:
        connection.execute('ALTER TABLE articles ADD COLUMN tags TEXT')
        connection.execute('UPDATE articles SET tags = ? WHERE id = 22', ('["共通", "共通", "技術"]',))
    assert client.get('/').status_code == 200
    assert client.get('/').status_code == 200
    with sqlite3.connect(browser.DB_PATH) as connection:
        assert 'tags' not in [row[1] for row in connection.execute('PRAGMA table_info(articles)')]
        assert connection.execute('SELECT COUNT(*) FROM article_tags').fetchone()[0] == 2
