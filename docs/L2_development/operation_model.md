# 運用モデル

`python summarize.py` が CLI の実行方法です（`summarize.py:190-205,309-310`）。既定では最大 5 件を処理し、`--ignore-history` は既存 URL の保存内容を上書きします（`summarize.py:194-204,276-284`）。RSS と記事の取得、Ollama API への接続が必要です（`summarize.py:14-16,148-150,216-217,248-250`）。

閲覧画面は `docker compose -f frontend/compose.yaml up --build` で起動し、`docker compose -f frontend/compose.yaml down` で停止します。ポート 8000 を公開し、DB を読み取り専用で参照します（`frontend/compose.yaml:1-10`、`frontend/app.py:25-29`）。認証はありません。CI の定義は未確認です。
