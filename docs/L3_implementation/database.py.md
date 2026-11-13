# database.py

SQLite の初期化時に articles の is_read を追加する。値は 0=未読、1=興味なし、2=興味あり、3=読んだ。タグは tags と article_tags に格納する。既存の articles.tags JSON をトランザクション内で移行し、列を削除する（database.py）。
