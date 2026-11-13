# Web エンドポイント

- `GET /`: 記事一覧。`q`、`feed`、`page` で検索、フィード選択、ページ移動を行います（`frontend/app.py:129-166`）。
- `GET /feeds`: フィード設定と最新の実行状態・ログを表示します（`frontend/app.py:60-66`）。
- `POST /feeds`: URL を取得・検証し、フィードタイトルと共に登録します（`frontend/app.py:43-57,69-87`）。
- `POST /feeds/<id>/settings`、`POST /feeds/<id>/delete`: フィード設定または削除を行います（`frontend/app.py:90-106`）。
- `POST /runs`: 非同期要約処理を開始し、重複実行を抑止します（`frontend/app.py:109-127`）。

認証はありません。登録時の接続先は利用者が指定します（`frontend/app.py:69-87`）。
