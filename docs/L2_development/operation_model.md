# 運用モデル

`python summarize.py` は登録済みフィードを処理します。`-n` は各フィードの設定を一時的に上書きし、`--ignore-history` は既存記事を再要約します（`summarize.py:185-200,231-257`）。新規 DB のフィードは空です（`database.py:18-23`）。

Web 画面は `docker compose -f frontend/compose.yaml up --build` で起動し、`docker compose -f frontend/compose.yaml down` で停止します。同時に自動取得用サービスも起動し、基本設定で有効にするとスケジュールに従って実行します。手動実行は自動取得の予定を変更しません（`scheduler.py:19-63`、`frontend/app.py:102-144`）。Linux のホストネットワークを使って Ollama と接続し、DB に書き込みます（`frontend/compose.yaml:1-14`）。認証はありません（`frontend/app.py:60-127`）。

テストは `PYTHONPATH=.:frontend python -m pytest -q frontend/tests` です（`frontend/tests/`）。CI 定義は確認されていません。
