# 整合性確認

`database.py` のテーブル定義、`summarize.py` の CLI とフィード処理、`frontend/app.py` のエンドポイントを README と L1・L3 に照合します。`docs/.ai/repo.profile.json` のコマンドと文書を相互に確認します。

Web と要約処理は `frontend/tests/` のテストで検証します。実際の RSS、ホスト Ollama、Docker 接続は実環境で確認が必要です（`frontend/compose.yaml`、`summarize.py:140`）。CI の定義は確認されていません。
