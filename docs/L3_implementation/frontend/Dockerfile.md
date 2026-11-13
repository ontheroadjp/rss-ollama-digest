# frontend/Dockerfile

Python イメージに Web、スケジューラー、要約処理の依存関係とソースを配置する。既定では Gunicorn を起動し、Compose のスケジューラーは command を上書きする（frontend/Dockerfile）。
