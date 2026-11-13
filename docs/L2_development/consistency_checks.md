# 整合性確認

`summarize.py` の定数、CLI 引数、テーブル定義、処理順序を README と L1・L3 の記述に照合します（`summarize.py:13-21,30-47,190-205,216-299`）。`docs/.ai/repo.profile.json` のコマンドと文書を相互に確認します。

閲覧画面の検索、ページ送り、DB 不在とリンクの扱いは `frontend/tests/test_app.py` で検証します。CI の定義は未確認です。
