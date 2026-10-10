# Contributing to Presek

Thank you for your interest in contributing to Presek! This document provides guidelines and best practices for contributing to the project.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Environment](#development-environment)
4. [Code Style Guidelines](#code-style-guidelines)
5. [Testing](#testing)
6. [Pull Request Process](#pull-request-process)
7. [Architecture Overview](#architecture-overview)
8. [Module Structure](#module-structure)
9. [Security Considerations](#security-considerations)
10. [Documentation Standards](#documentation-standards)

---

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md). Be respectful, inclusive, and professional in all interactions.

---

## Getting Started

### Prerequisites

- Python 3.13+
- Node.js 22+ (for frontend development)
- PostgreSQL 15+ with pgvector extension
- Redis 7+
- UV package manager

### Quick Start

```bash
# Clone the repository
git clone https://github.com/emiloffingen/presek.git
cd presek

# Set up Python environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync

# Set up frontend (optional, for web development)
cd web
npm install
cd ..

# Copy environment file
cp .env.example .env
# Edit .env with your local configuration

# Run database migrations
# Note: You'll need a running PostgreSQL instance

# Start development server
./start.sh
```

The development server will start:
- FastAPI backend on `http://localhost:8000`
- Frontend on `http://localhost:3000` (if running separately)

---

## Development Environment

### Using Docker Compose (Recommended for Backend)

```bash
# Start all backend services (Postgres, Redis, FastAPI, Celery)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

Note: The frontend (Astro) needs to be run separately with `cd web && npm run dev`.

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Required variables for development:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `SECRET_KEY` - Random secret (generate with `openssl rand -hex 32`)
- `JWT_SECRET` - JWT signing secret
- `CSRF_TOKEN_SECRET` - CSRF secret

---

## Code Style Guidelines

### Python Code Style

- **Formatter**: Ruff (configured in `pyproject.toml`)
- **Linter**: Ruff
- **Type Hints**: Required for all public functions and methods
- **Line Length**: 100 characters maximum
- **Imports**: Grouped by type (standard library, third-party, local), alphabetical within groups

```python
# Good example
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException

from core.database import db_manager as db
from utils.helpers import validate_input

router = APIRouter()


def process_data(data: Dict[str, Any]) -> Optional[List[str]]:
    """Process input data and return results."""
    if not data:
        return None
    return [str(item) for item in data.values()]
```

### Naming Conventions

- **Variables & Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private/Internal**: Prefix with `_` (single underscore)
- **Test Files**: `test_*.py`

### Docstrings

All public functions and classes must have docstrings following Google style:

```python
def calculate_score(article: Dict[str, Any], weight: float = 1.0) -> float:
    """Calculate the score for an article.

    Args:
        article: Dictionary containing article data with 'source', 'age', etc.
        weight: Multiplier for the base score (default: 1.0)

    Returns:
        float: The calculated score between 0.0 and 100.0

    Raises:
        ValueError: If article is missing required fields

    Example:
        >>> calculate_score({"source": "reliable", "age": 2})
        85.5
    """
    if not article:
        raise ValueError("Article cannot be empty")
    return 0.0
```

### Module Organization

- Keep modules focused on a single responsibility
- **Maximum module size**: ~1000 lines (split larger modules)
- Group related functionality together
- Avoid circular imports

---

## Testing

### Running Tests

```bash
# Run all tests
.venv/bin/python -m pytest -v

# Run specific test file
.venv/bin/python -m pytest tests/test_api_fast.py -v

# Run with coverage
.venv/bin/python -m pytest --cov=core --cov=routes --cov-report=html

# Run only unit tests (exclude integration tests)
.venv/bin/python -m pytest -v -m "not integration"

# Run with timeout (for slow tests)
.venv/bin/python -m pytest -v --timeout=30
```

### Writing Tests

- **Test Files**: Mirror the structure of the code they test
- **Test Functions**: Use `test_` prefix
- **Fixtures**: Use pytest fixtures for common test data
- **Coverage**: Aim for 80%+ test coverage

```python
# Good test example
import pytest
from fastapi.testclient import TestClient

from core.api_fast import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_db(mocker):
    return mocker.patch("core.database.db_manager")


class TestNewsEndpoints:
    """Tests for news-related API endpoints."""

    def test_get_news_returns_clusters(self, client, mock_db):
        """GET /news should return a list of clusters."""
        mock_db.async_execute.return_value = []

        response = client.get("/api/news")

        assert response.status_code == 200
        assert "clusters" in response.json()

    def test_get_news_filters_by_category(self, client, mock_db):
        """GET /news should filter by category parameter."""
        mock_db.async_execute.return_value = []

        response = client.get("/api/news?category=politics")

        assert response.status_code == 200
```

---

## Pull Request Process

### Before Submitting

1. **Run Tests**: Ensure all tests pass
   ```bash
   .venv/bin/python -m pytest -v
   ```

2. **Run Linter**: Ensure code follows style guidelines
   ```bash
   ruff check .
   ruff format .
   ```

3. **Type Check**: Run type checking
   ```bash
   mypy core/ routes/ utils/
   ```

4. **Security Scan**: Run security checks
   ```bash
   bandit -r .
   pip-audit
   ```

### Submitting a Pull Request

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes with descriptive messages
4. Push to your fork
5. Open a Pull Request to the main branch

### PR Requirements

- ✅ All tests pass
- ✅ Code follows style guidelines
- ✅ No security vulnerabilities introduced
- ✅ Documentation updated (if applicable)
- ✅ Clear commit messages
- ✅ Descriptive PR title and description

### PR Review Process

1. **Automated Checks**: CI pipeline runs tests, linting, and security scans
2. **Code Review**: Maintainers review the code
3. **Feedback**: Address any review comments
4. **Approval**: Requires at least one maintainer approval
5. **Merge**: Maintainer merges the PR

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                            Presek Architecture                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐  │
│  │   Frontend    │    │   FastAPI    │    │      Celery Workers   │  │
│  │   (Astro)     │◄───►│   Backend    │◄───►│   (Ingestion, AI, etc) │  │
│  └──────────────┘    └──────────────┘    └─────────────────────┘  │
│           ▲                  ▲  ▲  ▲  ▲  ▲                  ▲          │
│           │                  │  │  │  │  │                  │          │
│           ▼                  ▼  ▼  ▼  ▼  ▼                  ▼          │
│  ┌──────────────┐    ┌─────┐ ┌─────┐ ┌─────┐ ┌─────────┐ ┌─────────┐  │
│  │   Browser     │    │ PG  │ │Redis│ │R2   │ │Cloudflare│ │  SMTP   │  │
│  └──────────────┘    └─────┘ └─────┘ └─────┘ └─────────┘ └─────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: RSS feeds → Crawler → Article extraction → Database
2. **Processing**: Articles → Clustering → Synthesis → Summaries
3. **Serving**: Database → API → Frontend → User

### Service Components

| Service | Purpose | Port |
|---------|---------|------|
| FastAPI | REST API | 8000 |
| Astro | Frontend SSR | 3000 |
| Celery Worker | Background tasks | N/A |
| Celery Beat | Scheduled tasks | N/A |
| PostgreSQL | Primary database | 5432 |
| Redis | Caching & queues | 6379 |

---

## Module Structure

### Core Modules (`core/`)

| Module | Purpose |
|--------|---------|
| `api_fast.py` | FastAPI app setup and main routes |
| `database.py` | Database connections and queries |
| `config.py` | Configuration and environment variables |
| `ingestion.py` | RSS feed fetching and article ingestion |
| `ai_engine.py` | AI provider management and text generation |
| `clustering.py` | Article clustering and similarity |
| `embeddings.py` | Vector embeddings generation |
| `auth.py` | Authentication and JWT handling |
| `health.py` | Health checks and monitoring |
| `celery_app.py` | Celery task definitions |

### Route Modules (`routes/`)

| Module | Purpose | Routes |
|--------|---------|--------|
| `news.py` | News feed and search | `/news`, `/search` |
| `home.py` | Homepage and live feeds | `/`, `/live`, `/latest-wire` |
| `admin.py` | Admin dashboard | `/admin/*` |
| `security.py` | Security endpoints | `/csrf-token`, auth helpers |
| `stats.py` | Statistics and analytics | `/stats/*` |
| `system.py` | System endpoints | `/health`, `/metrics` |
| `profile.py` | User profiles | `/profile/*` |

### Utility Modules (`utils/`)

| Module | Purpose |
|--------|---------|
| `ranking.py` | Article and cluster ranking |
| `cache.py` | Caching utilities |
| `network.py` | HTTP client and network utilities |
| `time.py` | Time and date utilities |

### Frontend (`web/`)

- Astro-based SSR frontend
- Pages in `web/src/pages/`
- Components in `web/src/components/`
- Styles in `web/src/styles/`

---

## Security Considerations

### Security Best Practices

1. **Never commit secrets** to version control
2. **Validate all inputs** using the provided validation functions
3. **Use parameterized queries** for database operations
4. **Sanitize outputs** to prevent XSS
5. **Follow principle of least privilege** for service accounts

### Security Features Already Implemented

- ✅ JWT authentication with role-based access
- ✅ CSRF protection with HMAC tokens
- ✅ Content Security Policy (CSP) headers
- ✅ Rate limiting per IP and endpoint
- ✅ Input validation at all boundaries
- ✅ SSRF protection for URL fetching
- ✅ Security headers (HSTS, X-Frame-Options, etc.)

### Reporting Security Issues

If you discover a security vulnerability, please:
1. **Do not** open a public issue
2. Email: `security@presek.live`
3. Include steps to reproduce
4. Allow reasonable time for response before public disclosure

---

## Documentation Standards

### Code Documentation

1. **All public functions** must have docstrings
2. **All classes** must have docstrings
3. **Complex logic** should have inline comments
4. **Configuration options** should be documented in comments

### API Documentation

API endpoints should be documented in `docs/API_DOCUMENTATION.md`:
- Endpoint path and method
- Parameters with types and descriptions
- Request/response examples
- Authentication requirements
- Rate limiting information

### Architecture Decisions

Significant architecture decisions should be documented in `docs/adr/`:
- Numbered ADR files (e.g., `001-use-fastembed-for-local-ai.md`)
- Context and problem statement
- Decision and rationale
- Alternatives considered
- Consequences

---

## Versioning

Presek follows semantic versioning (SemVer):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward-compatible)
- **PATCH**: Bug fixes (backward-compatible)

Version is defined in `VERSION` file and `pyproject.toml`.

---

## Release Process

1. Update version in `VERSION` and `pyproject.toml`
2. Update `CHANGELOG.md` with new features and fixes
3. Run all tests and checks
4. Create Git tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
5. Push tag: `git push origin vX.Y.Z`
6. Build and deploy using deployment scripts

---

## License

By contributing to Presek, you agree that your contributions will be licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Getting Help

- **Documentation**: [README.md](README.md)
- **API Documentation**: [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)
- **Deployment Guide**: [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md)
- **Security Guidelines**: [SECURITY.md](SECURITY.md)

Have questions? Open an issue with the `question` label, or join our development discussions.

---

*Thank you for contributing to Presek!* 🎉
