# Web エンドポイント

- `GET /`: 設定されたタイムゾーンで記事日時を表示し、`q`、`feed`、`page` で検索、フィード選択、ページ移動を行います（`frontend/app.py:161-199`）。
- `GET /feeds`: 管理画面。`tab=basic` で基本設定、それ以外はフィード設定と実行状態を表示します（`frontend/app.py:78-86`）。
- `POST /settings/timezone`: 有効なタイムゾーンを保存します（`frontend/app.py:89-98`）。
- `POST /feeds`: URL を取得・検証し、フィードタイトルと共に登録します（`frontend/app.py:61-75,101-119`）。
- `POST /feeds/<id>/settings`、`POST /feeds/<id>/delete`: フィード設定または削除を行います（`frontend/app.py:122-138`）。
- `POST /runs`: 非同期要約処理を開始し、重複実行を抑止します（`frontend/app.py:141-158`）。

認証はありません。登録時の接続先は利用者が指定します（`frontend/app.py:101-119`）。
