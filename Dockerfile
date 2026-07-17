# Stage 1: Build Frontend
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency definitions
COPY frontend/package*.json ./frontend/

WORKDIR /app/frontend

# Install dependencies
RUN npm ci

# Copy frontend source files
COPY frontend/ ./

# Build the Vite application
RUN npm run build

# Stage 2: Serve Backend + Frontend
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by python-magic
RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

# Copy backend dependencies
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ ./backend/
COPY shared/ ./shared/

# Copy built frontend assets from builder
COPY --from=builder /app/frontend/dist ./frontend/dist

# Validate import graph during build
RUN python -c "import backend.main"

# Ensure we expand $PORT properly with shell form
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
