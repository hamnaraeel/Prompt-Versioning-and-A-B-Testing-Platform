FROM python:3.11-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Reuse the backend's app package so services/models/config stay in sync.
COPY backend/app ./app
COPY worker/worker.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "worker.py"]
