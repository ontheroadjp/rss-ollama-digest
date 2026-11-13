# 運用モデル

`python summarize.py` は登録済みフィードを処理します。`-n` は各フィードの設定を一時的に上書きし、`--ignore-history` は既存記事を再要約します（`summarize.py:185-200,231-257`）。新規 DB のフィードは空です（`database.py:18-23`）。

Web 画面は `docker compose -f frontend/compose.yaml up --build` で起動し、`docker compose -f frontend/compose.yaml down` で停止します。Linux のホストネットワークを使って Ollama と接続し、DB に書き込みます（`frontend/compose.yaml:1-14`）。認証はありません（`frontend/app.py:60-127`）。

テストは `PYTHONPATH=.:frontend python -m pytest -q frontend/tests` です（`frontend/tests/`）。CI 定義は確認されていません。
