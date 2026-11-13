# RSS Ollama Digest

RSS の記事本文を取得し、ローカルの Ollama で日本語に要約して SQLite に保存します（`summarize.py:190-310`）。

## Features

- RSS の記事を取得し、本文の抽出と要約を行います。処理済み URL は通常スキップします（`summarize.py:216-285`）。
- 任意の webhook への通知に対応します（`summarize.py:180-187,294-299`）。
- Docker で保存済み記事の一覧・検索をブラウザから利用できます。

## Installation

Python と `feedparser`、`requests`、`trafilatura` が必要です（`summarize.py:1-11`）。依存関係の固定ファイルは未確認です。Ollama の API とモデル `qwen3.5:4b` を利用できるようにしてください（`summarize.py:15-16,148-150`）。

## Usage

`python summarize.py` で実行します。`-n` で処理件数を指定でき、既定値は 5 です。`--ignore-history` は既存レコードを再要約して上書きします（`summarize.py:190-205,211-214,276-284`）。

閲覧画面は Docker Compose を使って `docker compose -f frontend/compose.yaml up --build` で起動し、同じPCでは <http://localhost:8000> を開きます。同じLAN内のスマートフォンからは、実行PCのIPアドレスを使って `http://<PCのIPアドレス>:8000` にアクセスします。IPアドレスは Linux なら `hostname -I` で確認できます。ファイアウォールが有効な場合はポート 8000 への接続を許可してください。

この画面には認証がなく、ポート 8000 に接続できる相手は保存済みの記事を閲覧できます。信頼できるネットワークで使用してください。リポジトリ直下の `summaries.db` を読み取り専用で参照します。終了するには `docker compose -f frontend/compose.yaml down` を実行します。DB がない場合は先に `python summarize.py` を実行してください。

## Design Principles

- URL を一意に保存し、通常は記事のダウンロード前に処理済みか確認します（`summarize.py:35-38,240-243`）。
- モデルへの入力は本文の先頭 4000 文字に制限します。コード内の説明では CPU での処理速度とのバランスを目的としています（`summarize.py:17,84-96`）。

## Configuration

RSS URL、Ollama URL、モデル名、通知先は `summarize.py:13-21` の定数で設定します。通知先が空の場合、通知は送信されません（`summarize.py:180-182`）。
