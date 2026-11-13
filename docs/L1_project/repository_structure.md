# リポジトリ構造

- `summarize.py`: CLI、フィード取得、要約、保存と通知（`summarize.py:175-324`）。
- `database.py`: SQLite テーブルの初期化と列追加（`database.py:6-32`）。
- `frontend/`: Flask アプリ、テンプレート、スタイル、Docker 設定とテスト（`frontend/app.py`、`frontend/Dockerfile`、`frontend/tests/`）。
- `summaries.db`: 実行時の既定 DB。Git 管理外（`summarize.py:20-21`、`.gitignore`）。
- `docs/`: 設計・運用・実装文書。

CI 定義とモノレポ構成は確認されていません。
