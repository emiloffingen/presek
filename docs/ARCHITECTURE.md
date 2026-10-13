# Presek Architecture Documentation

This document provides a comprehensive overview of Presek's architecture, design decisions, and component interactions.

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Module Structure](#module-structure)
6. [API Design](#api-design)
7. [Background Processing](#background-processing)
8. [Caching Strategy](#caching-strategy)
9. [Security Architecture](#security-architecture)

---

## System Overview

Presek is a **news aggregation and analysis platform** that collects, processes, and presents news articles from multiple sources with intelligent clustering, synthesis, and analysis capabilities.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              PRESEK SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                        USER INTERFACE LAYER                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │   Web Browser  │  │   Mobile App  │  │    API Clients (3rd party)  │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  │                          ▲   ▲   ▲                               ▲          │   │
│  │                          │   │   │                               │          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    ▲   ▲   ▲                           ▲          │
│                                    │   │   │                           │          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       PRESENTATION LAYER                              │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                    Astro Frontend (SSR)                         │  │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐  │  │   │
│  │  │  │   Pages      │  │  Components   │  │   Styles (Tailwind)    │  │  │   │
│  │  │  └─────────────┘  └─────────────┘  └──────────────────────┘  │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │                                                                    │  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                      Nginx Reverse Proxy                         │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │          │
│                                    │                                        │          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       APPLICATION LAYER                               │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                      FastAPI Backend                            │  │   │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │  │   │
│  │  │  │  Routes   │  │  Core     │  │  Utils    │  │  NLP          │  │  │   │
│  │  │  │  /news   │  │  /api     │  │  /ranking │  │  /categories  │  │  │   │
│  │  │  │  /home   │  │  /auth    │  │  /cache   │  │  /entities    │  │  │   │
│  │  │  │  /admin  │  │  /db      │  │  /time    │  │  /text       │  │  │   │
│  │  │  │  /stats  │  │  /config  │  │  /network │  │               │  │  │   │
│  │  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  │                                                                    │  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                      Celery Task Queue                          │  │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │  │   │
│  │  │  │  Ingestion    │  │  Intel-heavy  │  │   Fast-track          │  │  │   │
│  │  │  │  Worker       │  │  Worker       │  │   Worker              │  │  │   │
│  │  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │  │   │
│  │  │                                                                    │  │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │  │   │
│  │  │  │  Delivery     │  │  Maintenance  │  │   Beat (Scheduler)     │  │  │   │
│  │  │  │  Worker       │  │  Worker       │  │                       │  │  │   │
│  │  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │          │
│                                    │                                        │          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       DATA LAYER                                    │   │
│  │  ┌─────────────────────────┐  ┌─────────────────────────────────┐  │   │
│  │  │    PostgreSQL (Primary)   │  │        Redis (Cache + Queue)       │  │   │
│  │  │  ┌─────────────────────┐  │  ┌─────────────────────────────┐  │  │   │
│  │  │  │  articles table       │  │  │  Key-Value Cache              │  │  │   │
│  │  │  │  clusters table        │  │  │  Celery Queue                 │  │  │   │
│  │  │  │  cluster_summaries     │  │  │  Rate Limiting                 │  │  │   │
│  │  │  │  knowledge_entities    │  │  │  Session Storage              │  │  │   │
│  │  │  │  source_health          │  │  │  Nonce Cache                  │  │  │   │
│  │  │  │  page_visits           │  │  └─────────────────────────────┘  │  │   │
│  │  │  └─────────────────────┘  │                                    │  │   │
│  │  │  pgvector extension       │  │                                    │  │   │
│  │  └─────────────────────────┘  └─────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       EXTERNAL SERVICES                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │  Cloudflare  │  │  AI Providers │  │    Email (SMTP)            │  │   │
│  │  │  (CDN, AI)   │  │  (Local, NVIDIA,│  │                            │  │   │
│  │  │             │  │   Groq, etc.) │  │                            │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Frontend Layer (Astro)

**Location**: `web/`

**Responsibilities**:
- Server-side rendering (SSR) for SEO and performance
- Static site generation for cacheable pages
- Responsive design with Tailwind CSS
- Client-side interactivity (minimal JavaScript)

**Key Components**:
- `web/src/pages/` - Page components (Astro)
- `web/src/components/` - Reusable UI components
- `web/src/styles/` - Global styles
- `web/public/` - Static assets

### 2. API Layer (FastAPI)

**Location**: `core/api_fast.py`, `routes/`

**Responsibilities**:
- RESTful API endpoints
- Request validation and authentication
- Response formatting and serialization
- Rate limiting and security headers
- Prometheus metrics exposure

**Route Modules**:
- `routes/news.py` - News feed and search
- `routes/home.py` - Homepage and live feeds
- `routes/admin.py` - Admin dashboard
- `routes/stats.py` - Statistics and analytics
- `routes/system.py` - Health checks and system info
- `routes/profile.py` - User profiles
- `routes/security.py` - Security endpoints

### 3. Core Services

**Location**: `core/`

| Module | Responsibility |
|--------|---------------|
| `api_fast.py` | FastAPI app initialization, middleware, routing |
| `database.py` | Database connections, query builders, migrations |
| `config.py` | Configuration management, environment variables |
| `ingestion.py` | RSS feed fetching, article extraction, storage |
| `ai_engine.py` | AI provider management, text generation, prompts |
| `clustering.py` | Article similarity, clustering algorithms |
| `embeddings.py` | Vector embeddings (local fastembed, remote APIs) |
| `auth.py` | JWT authentication, token management |
| `health.py` | Health checks, monitoring, metrics |
| `celery_app.py` | Celery task definitions and configuration |
| `llm_router.py` | AI provider routing and fallback logic |
| `queue_monitoring.py` | Celery queue health monitoring |
| `trust_signals.py` | Source trust and credibility scoring |

### 4. Utility Modules

**Location**: `utils/`

| Module | Responsibility |
|--------|---------------|
| `ranking.py` | Article and cluster scoring/ranking |
| `cache.py` | Caching utilities and decorators |
| `network.py` | HTTP client, request utilities, safe fetching |
| `time.py` | Date/time utilities and parsing |
| `db_helpers.py` | Database helper functions |
| `metadata.py` | Metadata extraction and processing |

### 5. NLP Modules

**Location**: `nlp/`

| Module | Responsibility |
|--------|---------------|
| `categories.py` | Category detection and classification |
| `entities.py` | Named entity recognition |
| `utils.py` | Text processing utilities |

### 6. Background Processing (Celery)

**Location**: `core/celery_app.py`, `tasks/`

**Worker Types**:

1. **Ingestion Worker** (`presek-worker-ingestion`)
   - Fetches RSS feeds
   - Extracts article content
   - Stores in database
   - Must run: Yes - No new articles without it

2. **Intel-Heavy Worker** (`presek-worker`)
   - Clustering articles
   - Generating summaries
   - AI synthesis
   - Must run: Yes - Synthesis backlog grows

3. **Fast-Track Worker** (`presek-worker-fasttrack`)
   - Breaking news summaries
   - Quick follow-ups
   - Must run: Mostly - Breaking news slow without it

4. **Delivery Worker** (`presek-worker-delivery`)
   - Newsletter delivery
   - Push notifications
   - Must run: Yes - Delivery stops

5. **Maintenance Worker** (`presek-worker-maintenance`)
   - Database cleanup
   - Backfill operations
   - Must run: Yes - Maintenance stalls

6. **Beat Scheduler** (`presek-beat`)
   - Scheduled tasks
   - Must run: Yes - Scheduled tasks stop

---

## Data Flow

### 1. Article Ingestion Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  RSS     │────▶│  Feed        │────▶│  Article    │────▶│  Database   │
│  Feeds   │     │  Fetcher     │     │  Extractor   │     │  (Postgres) │
└─────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                            Article Processing                            │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐  │
│  │  Clean       │────▶│  Extract     │────▶│  Store in articles   │  │
│  │  HTML/Text   │     │  Metadata    │     │  table               │  │
│  └─────────────┘     └─────────────┘     └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Clustering Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  New        │────▶│  Similarity  │────▶│  Cluster     │
│  Articles   │     │  Calculation │     │  Formation   │
└─────────────┘     └─────────────┘     └─────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Cluster Processing                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐  │
│  │  Score       │     │  Generate    │     │  Store summary      │  │
│  │  Cluster     │────▶│  Summary    │────▶│  in cluster_summaries│  │
│  └─────────────┘     └─────────────┘     └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. API Request Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Client     │────▶│  Nginx       │────▶│  FastAPI     │
│  Request    │     │  (Reverse    │     │  (Backend)   │
└─────────────┘     │   Proxy)     │     └─────────────┘
                     └─────────────┘            │
                                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Request Processing                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐  │
│  │  Middleware │────▶│  Route       │────▶│  Database Query     │  │
│  │  (Auth,     │     │  Handler     │     │  or Cache Lookup     │  │
│  │   CORS,     │     │              │     │                      │  │
│  │   Rate      │     │              │     │                      │  │
│  │   Limit)    │     │              │     │                      │  │
│  └─────────────┘     └─────────────┘     └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Response Flow                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐  │
│  │  Format      │────▶│  Add         │────▶│  Return to Client    │  │
│  │  Response    │     │  Headers     │     │                      │  │
│  └─────────────┘     │  (Security,  │     └─────────────────────┘  │
│                     │   CSP, etc.)  │                                  │
│                     └─────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

### Core Module (`core/`)

The `core/` directory contains the main application logic, organized by concern:

```
core/
├── __init__.py           # Package initialization
├── api_fast.py           # FastAPI app setup, middleware, main router
├── api_helpers.py        # API helper functions
├── auth.py               # JWT authentication utilities
├── celery_app.py         # Celery application and task definitions
├── clustering.py         # Article clustering algorithms
├── config.py             # Configuration and environment variables
├── database.py           # Database connections and query utilities
├── embeddings.py         # Vector embedding generation
├── health.py             # Health checks and monitoring
├── ingestion.py          # RSS feed ingestion and article processing
├── ai_engine.py          # AI provider management and text generation
├── llm_router.py         # AI provider routing logic
├── queue_monitoring.py   # Celery queue health monitoring
├── trust_signals.py       # Source trust and credibility scoring
├── version.py            # Version information
└── ...
```

### Routes Module (`routes/`)

The `routes/` directory contains FastAPI route handlers, organized by endpoint category:

```
routes/
├── __init__.py           # Package initialization, router aggregation
├── admin.py              # Admin dashboard endpoints
├── common.py             # Common utilities for routes
├── curation.py           # Curation heuristics and filters
├── home.py               # Homepage and live feed endpoints
├── marketing.py          # Marketing-related endpoints
├── news.py               # News feed and search endpoints
├── profile.py            # User profile endpoints
├── security.py           # Security-related endpoints (CSRF, etc.)
├── stats.py              # Statistics and analytics endpoints
└── system.py             # System endpoints (health, metrics, etc.)
```

### Utils Module (`utils/`)

The `utils/` directory contains utility functions and helpers:

```
utils/
├── __init__.py           # Package initialization
├── cache.py              # Caching utilities
├── db_helpers.py         # Database helper functions
├── metadata.py           # Metadata extraction utilities
├── network.py            # Network and HTTP utilities
├── ranking.py            # Ranking and scoring algorithms
└── time.py               # Date/time utilities
```

---

## API Design

### RESTful Principles

Presek follows RESTful API design principles:

- **Resource-based**: URLs represent resources (nouns, not verbs)
- **HTTP Methods**: Proper use of GET, POST, PUT, DELETE
- **Stateless**: No server-side session state
- **Standard Status Codes**: 200, 201, 400, 401, 403, 404, 429, 500
- **JSON Responses**: Consistent JSON response format

### API Versioning

- **Current Version**: v1 (no version prefix in URLs currently)
- **Version Strategy**: URL path versioning (e.g., `/api/v2/news`)
- **Backward Compatibility**: New versions maintain backward compatibility where possible

### Response Format

All API responses follow a consistent format:

```json
{
  "status": "success|error",
  "data": { ... },  // Optional for success responses
  "message": "Human-readable message",  // Optional
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description",
    "details": { ... }  // Optional additional error details
  }
}
```

### Error Handling

Presek uses a standardized error handling approach:

- **API Errors**: Custom exception class with consistent formatting
- **HTTP Exceptions**: Proper HTTP status codes
- **Error Details**: Include field-level validation errors when applicable
- **Logging**: All errors are logged with context

See `core/api_errors.py` for error handling implementation.

### Authentication

Presek uses JWT-based authentication:

- **Token Type**: Bearer tokens in Authorization header
- **Algorithm**: HS256 (HMAC-SHA256)
- **Token Lifetime**: Configurable (default: 60 minutes)
- **Refresh**: No automatic refresh (re-authenticate after expiry)

**Admin Authentication**:
- Static admin tokens (configurable via `PRESEK_ADMIN_TOKEN`)
- JWT tokens with admin role

**CSRF Protection**:
- Required for state-changing operations (POST, PUT, DELETE)
- Token-based with automatic cookie setting
- Exempt for GET, HEAD, OPTIONS

---

## Background Processing

### Celery Task Queue

Presek uses Celery for background task processing with Redis as the message broker.

**Task Types**:

1. **Periodic Tasks** (Scheduled via Celery Beat)
   - Feed ingestion (every 15 minutes)
   - Cluster synthesis (every 30 minutes)
   - Health checks (every 5 minutes)
   - Newsletter delivery (daily)
   - Backup verification (daily)

2. **On-Demand Tasks**
   - Article ingestion (triggered by feed fetcher)
   - Cluster synthesis (triggered by new articles)
   - Image processing
   - Audio generation

3. **Deferred Tasks**
   - Synthesis upgrades (when queues are full)
   - Maintenance operations

### Queue Configuration

| Queue Name | Priority | Purpose |
|------------|----------|---------|
| ingestion | High | RSS feed fetching and article extraction |
| intel-heavy | Medium | AI synthesis and clustering |
| fast-track | Medium | Breaking news processing |
| delivery | Medium | Newsletter and notification delivery |
| maintenance | Low | Database cleanup and backfill |

### Task Retry and Error Handling

- **Max Retries**: 3 attempts by default
- **Retry Delay**: Exponential backoff (1s, 2s, 4s, ...)
- **Error Tracking**: Failed tasks are logged and tracked
- **Dead Letter Queue**: Tasks that fail after max retries go to DLQ

---

## Caching Strategy

### Cache Layers

1. **Redis Cache** (Primary)
   - Key-value caching for API responses
   - Session storage
   - Rate limiting counters
   - Nonce storage for CSP

2. **Database Cache**
   - Materialized views for common queries
   - Indexes for performance-critical queries
   - pgvector for vector similarity search

3. **Application Cache**
   - In-memory caching for frequently accessed data
   - Request-level caching for repeated operations

### Cache Keys

Cache keys follow a consistent naming convention:

```
api:{endpoint}:{params_hash}
api:news:v2:{q}:{category}:{topic}:{page}:{page_size}
cache:source_health:{country}
cache:trending_topics:{timespan}
```

### Cache Invalidation

- **Time-based**: Automatic expiration (TTL)
- **Event-based**: Manual invalidation on data changes
- **Version-based**: Cache key includes version/hash for content changes

---

## Security Architecture

### Security Layers

1. **Network Layer**
   - TLS/SSL encryption (HTTPS)
   - Cloudflare CDN with DDoS protection
   - IP-based rate limiting

2. **Application Layer**
   - JWT authentication
   - CSRF protection
   - Input validation
   - Security headers (CSP, HSTS, etc.)

3. **Data Layer**
   - Parameterized queries (prevent SQL injection)
   - Output encoding (prevent XSS)
   - Sensitive data protection

### Security Headers

Presek implements comprehensive security headers:

```
# Content Security Policy (CSP)
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; img-src 'self' data: https:; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'

# Other Security Headers
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Referrer-Policy: no-referrer-when-downgrade
Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

### Authentication Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  Client │────▶│  Login       │────▶│  Generate    │
│         │     │  (if needed) │     │  JWT Token   │
└─────────┘     └─────────────┘     └─────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Token Usage                                     │
│  ┌─────────┐     ┌─────────────┐     ┌──────────────────────────┐  │
│  │  Client │────▶│  Include     │────▶│  Server validates and      │  │
│  │         │     │  Token in    │     │  processes request         │  │
│  └─────────┘     │  Authorization│     └──────────────────────────┘  │
│                 │  Header       │                                  │
│                 └─────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

### CSRF Protection Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  Client │────▶│  GET         │────▶│  Server      │
│         │     │  /csrf-token │     │  generates    │
└─────────┘     └─────────────┘     │  CSRF token   │
                                     └─────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Token Storage                                   │
│  ┌─────────┐     ┌─────────────┐     ┌──────────────────────────┐  │
│  │  Server │────▶│  Set         │────▶│  Client stores token      │  │
│  │         │     │  Cookie      │     │  (in cookie or local storage)│  │
│  └─────────┘     └─────────────┘     └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  Client │────▶│  POST        │────▶│  Server      │
│         │     │  (with token)│     │  validates    │
└─────────┘     └─────────────┘     │  CSRF token   │
                                     └─────────────┘
```

---

## Production Deployment

### Deployment Options

1. **Manual Deployment**
   - Direct installation on server
   - Systemd service management
   - Nginx reverse proxy

2. **Container Deployment**
   - Docker containers for each service
   - Docker Compose for local development
   - Kubernetes for production (future)

### Systemd Services

Presek runs as a systemd target (`presek.target`) with individual services:

| Service | Description | Required |
|---------|-------------|----------|
| `presek-fastapi-unified` | FastAPI backend | Yes |
| `presek-astro` | Astro frontend SSR | Yes |
| `presek-worker-ingestion` | Ingestion worker | Yes |
| `presek-worker` | Intel-heavy worker | Yes |
| `presek-beat` | Celery beat scheduler | Yes |
| `presek-worker-fasttrack` | Fast-track worker | Mostly |
| `presek-worker-delivery` | Delivery worker | Yes |
| `presek-worker-maintenance` | Maintenance worker | Yes |

### Monitoring and Observability

- **Prometheus Metrics**: Exposed at `/api/metrics`
- **Health Checks**: Available at `/api/health`
- **Logging**: Structured logging with JSON format
- **Error Tracking**: Sentry integration for error reporting
- **Tracing**: OpenTelemetry for distributed tracing

### Scaling Considerations

- **Horizontal Scaling**: FastAPI and Celery workers can be scaled horizontally
- **Database**: PostgreSQL with read replicas for scaling reads
- **Caching**: Redis cluster for high-availability caching
- **Queue**: Multiple Celery workers for parallel processing

---

## Configuration

### Environment Variables

Presek uses environment variables for configuration. See `.env.example` for all available options.

**Required Variables**:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `SECRET_KEY` - Application secret key
- `JWT_SECRET` - JWT signing secret
- `CSRF_TOKEN_SECRET` - CSRF token secret

**Optional Variables**:
- `PRESEK_ADMIN_TOKEN` - Admin API token
- `AI_ENABLED` - Enable/disable AI features
- `PROVIDER_FALLBACK_ORDER` - AI provider priority
- `LOG_LEVEL` - Logging level
- `ENV` - Environment (development, staging, production)

### Configuration Files

- `pyproject.toml` - Python project configuration and dependencies
- `docker-compose.yml` - Docker Compose configuration for development
- `alembic.ini` - Alembic migration configuration
- `deploy/` - Deployment scripts and configurations

---

## Performance Considerations

### Performance Optimizations

1. **Database**
   - Proper indexing on frequently queried columns
   - pgvector for efficient vector similarity search
   - Connection pooling for database connections

2. **Caching**
   - Redis caching for API responses
   - Cache TTL based on data volatility
   - Cache invalidation on data changes

3. **AI Processing**
   - Local embeddings (fastembed) for cost savings
   - Multi-provider fallback for reliability
   - Async processing for non-blocking operations

4. **Frontend**
   - Server-side rendering (SSR) for SEO and performance
   - Static site generation for cacheable pages
   - Lazy loading for non-critical resources

### Performance Metrics

Key performance metrics to monitor:
- API response times (p50, p90, p99)
- Database query times
- Cache hit rates
- Queue processing times
- Error rates

---

## Troubleshooting

Common issues and their solutions:

1. **Database Connection Issues**
   - Check `DATABASE_URL` environment variable
   - Verify PostgreSQL is running
   - Check network connectivity

2. **Redis Connection Issues**
   - Check `REDIS_URL` environment variable
   - Verify Redis is running
   - Check Redis memory usage

3. **AI Provider Issues**
   - Check API keys are configured
   - Verify provider is available
   - Check rate limits

4. **Celery Worker Issues**
   - Check worker logs
   - Verify Redis is accessible
   - Check queue lengths

For detailed troubleshooting, see [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md).

---

## Future Architecture Improvements

1. **Microservices**: Split into separate services (API, ingestion, AI)
2. **Kubernetes**: Container orchestration for production
3. **Service Mesh**: Istio or Linkerd for service-to-service communication
4. **Event Sourcing**: For audit trail and replay capability
5. **GraphQL**: Alternative API for complex queries
6. **WebSockets**: Real-time updates for live feeds

---

## References

- [README.md](../README.md) - Main project documentation
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - API endpoint documentation
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) - Deployment guide
- [OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md) - Operational procedures
- [SECURITY.md](../SECURITY.md) - Security documentation
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
