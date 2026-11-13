# テスト

`frontend/tests/test_app.py` は一時 SQLite DB と Flask テストクライアントを使い、登録検証、検索、フィルター、ページ送り、実行表示とタイムゾーン設定を確認します。`frontend/tests/test_summarize.py` は DB 移行、記事取得数、出典、日時の保存およびログを検証します。外部取得と要約はテスト内で模擬します。

pytest と `frontend/requirements.txt` の依存を用意し、`PYTHONPATH=.:frontend python -m pytest -q frontend/tests` を実行します。CI とカバレッジ方針は確認されていません。
