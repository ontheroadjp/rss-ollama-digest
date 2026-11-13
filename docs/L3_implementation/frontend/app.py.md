# frontend/app.py

Flask は検索、フィード・タグ・記事状態による絞り込み、日時順の一覧を提供する。記事状態を SQLite に保存し、非同期操作に JSON を返す。フィード管理、タイムゾーン設定と要約実行・停止も提供する（frontend/app.py）。
