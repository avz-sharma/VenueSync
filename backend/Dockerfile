# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Final
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by python-magic
RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Ensure local bin is on PATH
ENV PATH=/root/.local/bin:$PATH

# Expose dynamic port for Cloud Run
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
