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
# Pin uv version for reproducibility (check https://github.com/astral-sh/uv/releases for latest)
COPY --from=ghcr.io/astral-sh/uv:v0.4.24 /uv /uvx /bin/
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
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r presek && useradd -r -g presek presek

# Copy installed python dependencies
COPY --chown=presek:presek --from=python-builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH

# Copy application code
COPY --chown=presek:presek . .

# Copy built frontend assets
COPY --chown=presek:presek --from=node-builder /app/web/dist ./static/dist

# Switch to non-root user
USER presek

# Expose ports
EXPOSE 8000

# Set entrypoint (will be overridden in docker-compose for specific services)
CMD ["python", "api_fast.py"]
