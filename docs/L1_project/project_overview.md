# プロジェクト概要

RSS 記事を取得・抽出し、Ollama による日本語要約を SQLite に保存します（`summarize.py:190-193,216-217,248-285`）。処理済み URL の省略、再処理、任意の webhook 通知を備えます（`summarize.py:200-204,240-243,294-299`）。

Python と feedparser、requests、trafilatura を使用します（`summarize.py:1-11`）。要約側の依存バージョンは未固定です。閲覧画面は Flask と Gunicorn を使い、Docker で実行します（`frontend/requirements.txt:1-2`、`frontend/Dockerfile:1-10`）。
