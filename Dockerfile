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
FROM python:3.12-slim AS python-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make cmake git python3-dev libpq-dev && \
    rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
# Install dependencies using uv into a .venv
RUN uv sync --frozen --no-dev --no-install-project


# --- Stage 3: Final Production Image ---
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r presek && useradd -r -g presek presek

# Copy installed python dependencies
COPY --from=python-builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH

# Copy application code
COPY . .

# Copy built frontend assets
COPY --from=node-builder /app/web/dist ./static/dist

# Set ownership for all files
RUN chown -R presek:presek /app

# Switch to non-root user
USER presek

# Expose ports
EXPOSE 8000

# Set entrypoint (will be overridden in docker-compose for specific services)
CMD ["python", "api_fast.py"]
