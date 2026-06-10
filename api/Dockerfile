# Container image for the FastAPI backend (Render / Railway / Fly / Cloud Run).
FROM python:3.11-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api ./api

EXPOSE 8000
# Set DATABASE_URL to your Supabase Session pooler URI — API reads from Postgres.
CMD ["uvicorn", "main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000"]
