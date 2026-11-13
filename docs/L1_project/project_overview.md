# プロジェクト概要

登録済み RSS フィードの記事を取得・抽出し、本文、Ollama による日本語要約と最大3件のタグを SQLite に保存します（`summarize.py:264-337`）。Web 画面はフィード・タイムゾーンの管理、DB容量表示、実行と中止、ログ表示と記事の検索・フィルターを提供します（`frontend/app.py:80-88,143-168,171-208`）。CLI と Web は共通 DB を利用します（`database.py:6-35`）。

Python、feedparser、requests、trafilatura、Flask、Gunicorn、tzdata を使用します。Flask と Gunicorn のバージョンは固定され、その他の依存は固定されていません（`frontend/requirements.txt:1-6`）。
