FROM python:3.13-slim

WORKDIR /app

# Install dependencies first — separate layer for Docker cache efficiency
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY ingestion/ ./ingestion/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Railway overrides this via railway.toml startCommand with $PORT
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
