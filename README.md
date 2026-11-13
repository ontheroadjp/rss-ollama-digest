# RSS Ollama Digest

RSS の記事本文を取得し、ローカルの Ollama で日本語に要約して SQLite に保存します（`summarize.py:190-310`）。

## Features

- RSS の記事を取得し、本文の抽出と要約を行います。処理済み URL は通常スキップします（`summarize.py:216-285`）。
- 任意の webhook への通知に対応します（`summarize.py:180-187,294-299`）。

## Installation

Python と `feedparser`、`requests`、`trafilatura` が必要です（`summarize.py:1-11`）。依存関係の固定ファイルは未確認です。Ollama の API とモデル `qwen3.5:4b` を利用できるようにしてください（`summarize.py:15-16,148-150`）。

## Usage

`python summarize.py` で実行します。`-n` で処理件数を指定でき、既定値は 5 です。`--ignore-history` は既存レコードを再要約して上書きします（`summarize.py:190-205,211-214,276-284`）。

## Design Principles

- URL を一意に保存し、通常は記事のダウンロード前に処理済みか確認します（`summarize.py:35-38,240-243`）。
- モデルへの入力は本文の先頭 4000 文字に制限します。コード内の説明では CPU での処理速度とのバランスを目的としています（`summarize.py:17,84-96`）。

## Configuration

RSS URL、Ollama URL、モデル名、通知先は `summarize.py:13-21` の定数で設定します。通知先が空の場合、通知は送信されません（`summarize.py:180-182`）。
