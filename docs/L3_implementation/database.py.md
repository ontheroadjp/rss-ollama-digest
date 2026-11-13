# database.py

SQLite の articles、feeds、settings、runs、run_logs を初期化し、既存 DB にフィード情報と記事の出典欄を追加する。settings は表示タイムゾーンを保持する。新規 DB のフィード一覧は空で、実行中ジョブは一意制約で1件に限定する（`database.py`）。

記事の抽出本文、フィード内 GUID、JSON 形式のタグ列を追加する。停止待ちも実行中として一意制約に含める（`database.py`）。
