# RSS Ollama Digest

RSS の記事本文を取得し、Ollama で日本語に要約して SQLite に保存します（`summarize.py:185-324`）。

## Features

- フィードの登録・検証・タイトル変更・削除と、フィードごとの取得数設定（`frontend/app.py:43-107`）。
- 登録済みフィードの記事取得と要約、Web からの即時実行と進捗表示（`summarize.py:215-324`、`frontend/templates/feeds.html`）。
- 記事一覧の検索、フィード選択、投稿日時順とページ送り（`frontend/app.py:129-166`）。
- 任意の webhook 通知（`summarize.py:175-182`）。
- 管理画面の基本設定で表示タイムゾーンを選択できます。既定は日本時間です（`frontend/app.py:22-44,78-98`）。

## Installation

Python と `frontend/requirements.txt` の依存関係、pytest（テスト用）、利用可能な Ollama と `qwen3.5:4b` が必要です（`frontend/requirements.txt`、`summarize.py:16-17`）。Docker を利用する場合は依存関係がイメージにインストールされます（`frontend/Dockerfile`）。

## Usage

Linux で `docker compose -f frontend/compose.yaml up --build` を実行し、`http://localhost:8000` を開きます。フィード登録ページで URL を追加し、「すぐに実行」を押します。新規 DB にはフィードがありません。停止は `docker compose -f frontend/compose.yaml down` です。Compose はホストネットワークを使い、ホストの Ollama に接続します（`frontend/compose.yaml:1-14`）。

CLI では `python summarize.py` を実行します。`-n 5` はフィードごとの取得数を今回の実行に限り上書きし、省略時は各フィードの設定（既定は無制限）を使います。`--ignore-history` は保存済み記事も再要約します（`summarize.py:189-200,231-257`）。

テストは pytest と依存関係を用意し、`PYTHONPATH=.:frontend python -m pytest -q frontend/tests` を実行します（`frontend/tests/`）。

Web 画面には認証がありません。接続できる人はフィードの変更と要約の実行ができます。信頼できるネットワークで使用してください（`frontend/app.py:60-127`）。

## Design Principles

- 記事 URL を一意に保存し、通常は本文のダウンロード前に処理済みか確認します（`database.py:8-11`、`summarize.py:39-42,255-259`）。
- モデルへの入力は本文の先頭 4000 文字に制限します。コードは CPU 処理速度とのバランスを理由に挙げています（`summarize.py:18,75-76`）。

## Configuration

フィード URL と取得数、表示タイムゾーンは管理画面で設定します。RSS の公開日時は元の値を保持して表示時に変換します。タイムゾーン情報のない既存日時は UTC として扱います（`frontend/app.py:25-44`）。`DATABASE_PATH` と `OLLAMA_URL` は環境変数で設定できます。モデル名と webhook の通知先は `summarize.py` の定数で設定します。通知先が空の場合は送信しません（`summarize.py:16-22,175-182`）。
