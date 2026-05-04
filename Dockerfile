# Dockerfile for Presek
# Multi-stage build to keep the production image small

# --- Stage 1: Build Node.js assets ---
FROM node:22-alpine AS node-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm install
COPY web/ .
RUN npm run build

# --- Stage 2: Build Python environment ---
FROM python:3.11-slim AS python-builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make cmake git python3-dev libpq-dev && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# Install pip and use only-binary for heavy ML packages
RUN pip install --no-cache-dir --user --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt


# --- Stage 3: Final Production Image ---
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies
COPY --from=python-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Copy built frontend assets
COPY --from=node-builder /app/web/dist ./static/dist

# Expose ports
EXPOSE 8000

# Set entrypoint (will be overridden in docker-compose for specific services)
CMD ["python", "api_fast.py"]
