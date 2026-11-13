FROM python:3.13-slim
WORKDIR /app
COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY database.py summarize.py scheduler.py ./
COPY frontend/app.py ./frontend/app.py
COPY frontend/templates ./frontend/templates
COPY frontend/static ./frontend/static
WORKDIR /app/frontend
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]
