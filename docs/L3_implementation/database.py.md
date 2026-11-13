# database.py

SQLite の articles、feeds、runs、run_logs を初期化し、既存 DB にフィード情報と記事の出典欄を追加する。新規 DB のフィード一覧は空で、実行中ジョブは一意制約で1件に限定する（`database.py`）。
