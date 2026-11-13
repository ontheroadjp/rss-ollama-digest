# database.py

SQLite の初期化と既存 DB の移行を行う。runs に実行元、開始・終了時刻、取得・要約件数を保持し、schedule_events に自動取得設定の変更を記録する。active run の一意制約は手動実行と自動実行の重複を防ぐ（database.py）。
