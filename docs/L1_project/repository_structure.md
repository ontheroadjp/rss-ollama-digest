# リポジトリ構造

- `summarize.py`: CLI、記事処理、保存、通知を実装します（`summarize.py:30-47,180-205,216-310`）。
- `summaries.db`: スクリプトが既定の保存先として参照する SQLite ファイルです（`summarize.py:19-20,211`）。
- `.gitignore`: インストール済み toolkit の一部と `AGENTS.md` を Git の対象から除外します（`.gitignore:1-8`）。
- `docs/`: この設計・運用文書を保持します。
- `frontend/`: SQLite を閲覧する Flask アプリ、画面、Docker 設定とテストを保持します（`frontend/app.py:20-41`、`frontend/compose.yaml:1-10`、`frontend/tests/test_app.py`）。

CI とモノレポ構成は確認できませんでした。要約処理の依存定義は未確認です。
