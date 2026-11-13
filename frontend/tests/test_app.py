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
