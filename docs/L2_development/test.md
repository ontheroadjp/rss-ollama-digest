# テスト

`frontend/tests/test_app.py` は Flask のテストクライアントと一時 SQLite DB を使い、検索・ページ送り、DB 不在、危険なリンクを検証します（`frontend/tests/test_app.py:7-44`）。pytest と `frontend/requirements.txt` の依存が必要です。CI の定義は確認されていません。
