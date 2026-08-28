FROM python:3.10-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    DATA_DIR=/app/data

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure data directory exists
RUN mkdir -p /app/data

EXPOSE 5000

# Run with Gunicorn (1 worker with threads for consistent singleton scheduler & queue locks)
CMD ["gunicorn", "--workers=1", "--threads=8", "--timeout=120", "--bind=0.0.0.0:5000", "app:app"]
