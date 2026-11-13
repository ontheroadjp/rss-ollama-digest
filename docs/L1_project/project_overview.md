# プロジェクト概要

登録済み RSS フィードの記事を取得・抽出し、Ollama による日本語要約を SQLite に保存します（`summarize.py:215-324`）。Web 画面は表示タイムゾーンとフィードの管理、即時実行、ログ表示と記事の検索・フィルターを提供します（`frontend/app.py:78-199`）。CLI と Web は共通 DB を利用します（`database.py:6-33`）。

Python、feedparser、requests、trafilatura、Flask、Gunicorn、tzdata を使用します。Flask と Gunicorn のバージョンは固定され、その他の依存は固定されていません（`frontend/requirements.txt:1-6`）。
