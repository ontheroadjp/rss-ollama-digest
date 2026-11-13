# プロジェクト概要

登録済み RSS フィードの記事を取得・抽出し、本文、Ollama による日本語要約と最大3件のタグを SQLite に保存します（`summarize.py:264-337`）。Web 画面はフィード・タイムゾーンと自動取得スケジュールの管理、DB容量表示、実行と中止、ログ表示と記事の検索・フィード・タグ・状態フィルターと状態の保存を提供します（`frontend/app.py:80-88,143-168,171-208`）。スケジューラーは別プロセスで動作し、CLI と Web は共通 DB を利用します（`database.py:6-35`）。

Python、feedparser、requests、trafilatura、Flask、Gunicorn、tzdata を使用します。Flask と Gunicorn のバージョンは固定され、その他の依存は固定されていません（`frontend/requirements.txt:1-6`）。
