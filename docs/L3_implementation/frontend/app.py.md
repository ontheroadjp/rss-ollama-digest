# 記事閲覧アプリ

Flask の `/` は SQLite の `articles` を読み取り専用で開き、タイトル・要約の部分一致検索と20件ずつのページ送りを提供する（`frontend/app.py:11-41`）。DB を開けない場合は 503 と案内を返す。リンクは HTTP / HTTPS に限定し、テンプレートは文字列をエスケープする（`frontend/app.py:15-17,40-41`、`frontend/templates/index.html`）。

DB パスは `DATABASE_PATH` で変更でき、既定値は `/data/summaries.db`。Compose はリポジトリを読み取り専用でマウントし、Gunicorn を介して LAN に公開する（`frontend/compose.yaml`、`frontend/Dockerfile`）。認証機能はない。
