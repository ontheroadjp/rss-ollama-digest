# frontend/tests/test_summarize.py

記事の公開日時を保持し、保存日時に UTC オフセットを付けることを検証する（`frontend/tests/test_summarize.py`）。

一時 SQLite DB と模擬 RSS を使用し、DB 移行、取得数、出典、既存記事の対応付けと実行ログを検証する（`frontend/tests/test_summarize.py`）。

本文・GUID・タグの保存、GUID 照合、タグ上限、実行開始前と要約中の停止を検証する（`frontend/tests/test_summarize.py`）。
