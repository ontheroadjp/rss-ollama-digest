# 運用モデル

`python summarize.py` が CLI の実行方法です（`summarize.py:190-205,309-310`）。既定では最大 5 件を処理し、`--ignore-history` は既存 URL の保存内容を上書きします（`summarize.py:194-204,276-284`）。RSS と記事の取得、Ollama API への接続が必要です（`summarize.py:14-16,148-150,216-217,248-250`）。

CI、ビルド、テストの定義は未確認です。定義ファイルの追加または所有者への確認が必要です。依存ライブラリは `summarize.py:9-11` を参照してください。
