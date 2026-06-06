# Container image for the FastAPI backend (Render / Railway / Fly / Cloud Run).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY data/processed ./data/processed

EXPOSE 8000
# DATABASE_URL drives the Postgres backend; without it the JSON snapshot is served.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
