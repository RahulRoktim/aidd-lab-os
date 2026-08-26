FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic requests

COPY . .

EXPOSE 8000

ENV PORT=8000 \
    AIDD_DB_PATH=/data/aidd_lab.db \
    AIDD_WORKER_URL=http://aidd-worker:8001

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
