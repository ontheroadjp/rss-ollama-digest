# Web エンドポイント

- `GET /`: 設定されたタイムゾーンで記事日時を表示し、`q`、`feed`、`tag`、`status`、`page` で検索、絞り込み、ページ移動を行います（`frontend/app.py:169-227`）。
- `POST /articles/<id>/read`: `is_read` に 1、2、3 を指定して記事状態を保存します。JSON を要求した場合は結果を返します（`frontend/app.py:230-240`）。
- `GET /feeds`: 管理画面。既定で基本設定を表示し、`tab=feeds` でフィード設定と実行状態を表示します（`frontend/app.py:78-86`）。
- `POST /settings/schedule`: 自動取得の無効・間隔・定時刻を保存します（`frontend/app.py:101-130`）。
- `POST /settings/timezone`: 有効なタイムゾーンを保存します（`frontend/app.py:89-98`）。
- `POST /feeds`: URL を取得・検証し、フィードタイトルと共に登録します（`frontend/app.py:61-75,101-119`）。
- `POST /feeds/<id>/settings`、`POST /feeds/<id>/delete`: フィード設定または削除を行います（`frontend/app.py:122-138`）。
- `POST /runs`: 非同期要約処理を開始し、重複実行を抑止します（`frontend/app.py:141-158`）。
- `POST /runs/<id>/stop`: 実行中または開始待ちの処理に停止を要求します（`frontend/app.py:163-168`）。

認証はありません。登録時の接続先は利用者が指定します（`frontend/app.py:101-119`）。
