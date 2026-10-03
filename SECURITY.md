# Presek Security Documentation

This document provides a comprehensive overview of the security features and best practices implemented in the Presek application.

## Table of Contents

1. [Authentication & Authorization](#authentication--authorization)
2. [Security Headers](#security-headers)
3. [CSRF Protection](#csrf-protection)
4. [Input Validation](#input-validation)
5. [Dependency Security](#dependency-security)
6. [Sensitive Data Protection](#sensitive-data-protection)
7. [API Security](#api-security)
8. [Database Security](#database-security)
9. [Security Testing](#security-testing)
10. [CI/CD Security](#cicd-security)

## Authentication & Authorization

### JWT Authentication

Presek uses JSON Web Tokens (JWT) for authentication with the following features:

- **Algorithm**: HS256 (HMAC with SHA-256)
- **Token Expiration**: Configurable (default: 60 minutes)
- **Claims**: Standard claims (`sub`, `iat`, `exp`, `jti`) plus custom claims
- **Secret Management**: Environment variable-based with fallback to secure generation

**Example Usage:**

```python
from core.auth import create_jwt_token, decode_jwt_token, verify_admin_jwt

# Create a token
token = create_jwt_token("username", {"role": "admin"})

# Verify a token
payload = decode_jwt_token(token)

# Verify admin token
is_admin = verify_admin_jwt(token)
```

**Environment Variables:**
- `JWT_SECRET`: Required for production, auto-generated for development
- `JWT_EXPIRE_MINUTES`: Token expiration time (default: 60)

### Role-Based Access Control

- **Admin Role**: Full access to administrative functions
- **User Role**: Standard user access
- **Middleware**: FastAPI dependency injection for route protection

## Security Headers

Presek implements comprehensive security headers through the `SecurityHeadersMiddleware`:

### Content Security Policy (CSP)

- **Nonce-based approach**: Allows inline scripts/styles with nonce attributes
- **Strict default**: `default-src 'self'`
- **Script sources**: `'self' 'nonce-{nonce}' https://cdn.jsdelivr.net`
- **Style sources**: `'self' 'nonce-{nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net`
- **No unsafe directives**: No `unsafe-inline` or `unsafe-eval`

### Other Security Headers

- **X-Content-Type-Options**: `nosniff`
- **X-Frame-Options**: `DENY`
- **Strict-Transport-Security**: `max-age=63072000; includeSubDomains; preload` (production)
- **Referrer-Policy**: `no-referrer-when-downgrade`
- **Permissions-Policy**: Restrictive permissions for sensors and devices
- **Cross-Origin Policies**: `same-origin` for opener, resource, and embedder policies

### Cookie Security

- **CSRF Token Cookie**: HttpOnly=False (accessible to JavaScript), Secure in production, SameSite=Lax
- **CSP Nonce Cookie**: HttpOnly=True, Secure in production, SameSite=Lax, short-lived (5 minutes)

## CSRF Protection

### Token Generation & Validation

```python
from routes.security import generate_csrf_token, validate_csrf_token

# Generate token
token = generate_csrf_token()

# Validate token
is_valid = validate_csrf_token(token)
```

### Features

- **HMAC-based tokens**: Using SHA-256
- **Timestamp-based expiry**: 1 hour validity
- **Automatic cookie setting**: CSRF token provided to frontend via cookie
- **Middleware protection**: Automatic validation for POST/PUT/DELETE requests
- **Exempt methods**: GET, HEAD, OPTIONS requests don't require CSRF tokens

### Implementation

1. **Token Generation**: HMAC(SHA-256) of timestamp + secret
2. **Token Validation**: Recompute HMAC and compare with constant-time comparison
3. **Expiry Check**: Tokens older than 1 hour are rejected
4. **Automatic Validation**: Middleware checks CSRF token in headers or form data

## Input Validation

### Validation Functions

Presek provides comprehensive input validation:

```python
from routes.security import (
    validate_cluster_id,
    validate_date,
    validate_email,
    validate_string_param,
    validate_list_param,
)

# Validate cluster ID (hex string, 6-64 chars)
cluster_id = validate_cluster_id("abc123")

# Validate date (YYYY-MM-DD format)
date_str = validate_date("2023-01-01")

# Validate email
email = validate_email("user@example.com")

# Validate string with length constraints
name = validate_string_param("test", "name", max_length=100)

# Validate list parameters
tags = validate_list_param(["tag1", "tag2"], "tags", max_items=10)
```

### Regex Patterns

- **Cluster ID**: `^[a-f0-9\-]{6,64}$`
- **UUID**: Standard UUID format
- **Date**: `^\d{4}-\d{2}-\d{2}$`
- **Email**: Comprehensive RFC-compliant pattern

### Request Size Limits

- **Max Request Body**: 10 MB
- **Max Query Parameter Length**: 1000 characters
- **Max Header Value Length**: 2000 characters

## Dependency Security

### Vulnerability Management

- **Automated Scanning**: `pip-audit` for Python dependencies
- **CI/CD Integration**: Security scans run on every push/PR
- **Ignored Vulnerabilities**: Documented exceptions for transitive dependencies

### Update Process

1. **Regular Scans**: Automated dependency vulnerability scanning
2. **Prioritized Updates**: Critical vulnerabilities addressed immediately
3. **Scheduled Updates**: Non-critical updates during maintenance windows

### Current Security Status

- ✅ No critical vulnerabilities
- ⚠️  32 non-critical updates available (as of 2026-06-04)
- ✅ All dependencies pinned to secure versions

## Sensitive Data Protection

### Environment Variables

**Required Variables:**
- `DATABASE_URL`: Database connection string
- `SECRET_KEY`: Application secret key
- `JWT_SECRET`: JWT signing secret

**Sensitive Variables:**
- `REDIS_URL`: Redis connection string
- `SMTP_PASS`: SMTP password
- `CLOUDFLARE_API_TOKEN`: Cloudflare API token
- `R2_SECRET_ACCESS_KEY`: R2 secret access key
- `CF_AI_GATEWAY_TOKEN`: Cloudflare AI gateway token

### Protection Measures

- **Validation**: Required variables validated on startup
- **Detection**: Automatic detection of default/test values
- **Documentation**: `.env.example` for reference
- **Git Ignore**: `.env` files excluded from version control

### File Permissions

- **Sensitive Files**: `.env`, private keys
- **Permission Check**: Automated verification of file permissions
- **Recommended**: `chmod 600` for sensitive files

## API Security

### Rate Limiting

- **Per-IP Tracking**: Prevents brute force attacks
- **Per-Endpoint Limits**: Customizable limits for different routes
- **Bypass**: Local development bypass for admin endpoints
- **Response**: `429 Too Many Requests` with `Retry-After` header

### Authentication Middleware

```python
from routes.security import admin_auth

@app.get("/admin/endpoint")
async def admin_endpoint(user: str = Depends(admin_auth)):
    return {"message": f"Hello {user}"}
```

### Error Handling

- **Secure Error Messages**: Generic error messages in production
- **Detailed Errors**: Only in development mode
- **HTTP Status Codes**: Proper status codes for all responses

## Database Security

### Connection Security

- **Parameterized Queries**: Via psycopg (PostgreSQL)
- **Connection Pooling**: Secure connection management
- **SSL Support**: Configurable SSL connections
- **Credential Management**: Environment-based credentials

### Data Protection

- **Sensitive Data**: Encrypted at rest (via PostgreSQL encryption)
- **Backup Security**: Regular encrypted backups
- **Data Retention**: Configurable retention policies

## Security Testing

### Automated Tests

**Core Security Tests:**
```bash
python tests/test_core_security.py
```

**Test Coverage:**
- ✅ CSRF token generation and validation
- ✅ Input validation patterns
- ✅ Environment variable validation
- ✅ Security constants verification
- ✅ Sensitive key detection

### Security Audit Script

```bash
python scripts/security_audit.py
```

**Audit Checks:**
- Python dependency vulnerabilities
- Node.js dependency vulnerabilities  
- Security headers configuration
- Content Security Policy validation
- Sensitive file detection
- File permission verification
- Environment variable security
- Database security configuration
- Dangerous code pattern detection

## CI/CD Security

### GitHub Actions Workflow

The CI/CD pipeline includes comprehensive security checks:

1. **Backend Tests**: Unit and integration tests
2. **Frontend Tests**: JavaScript tests and linting
3. **Security Scan**: Multiple security tools
4. **Load Testing**: Performance and stability testing
5. **Deployment**: Secure deployment process

### Security Scan Tools

- **Presek Security Audit**: Custom audit script
- **Trivy**: Vulnerability scanner for dependencies and containers
- **Bandit**: Python code security analyzer
- **Safety**: Python dependency vulnerability checker
- **Semgrep**: Code pattern analysis for security issues
- **Gitleaks**: Secret detection in code
- **Snyk**: Comprehensive dependency scanning

### Security Gates

- **Required for Merge**: All security checks must pass
- **Block Critical Issues**: Critical vulnerabilities block deployment
- **Automated Reporting**: Security scan results available in PRs

## Security Best Practices

### Development Guidelines

1. **Never commit secrets**: Use environment variables
2. **Validate all inputs**: Use provided validation functions
3. **Use HTTPS**: Always use secure connections
4. **Keep dependencies updated**: Regular vulnerability scanning
5. **Follow principle of least privilege**: Minimum necessary permissions

### Incident Response

1. **Detection**: Automated monitoring and alerts
2. **Containment**: Immediate isolation of affected systems
3. **Eradication**: Remove vulnerabilities and patch systems
4. **Recovery**: Restore services with enhanced security
5. **Lessons Learned**: Post-incident review and improvements

## Compliance

### OWASP Top 10 Coverage

| Risk | Status | Implementation |
|------|--------|----------------|
| A01: Broken Access Control | ✅ | JWT authentication, role-based access |
| A02: Cryptographic Failures | ✅ | Secure JWT with HS256, proper key management |
| A03: Injection | ✅ | Input validation, parameterized queries, CSP |
| A04: Insecure Design | ✅ | Secure defaults, proper error handling |
| A05: Security Misconfiguration | ✅ | Comprehensive security headers, CSP |
| A06: Vulnerable Components | ✅ | Dependency scanning, update process |
| A07: Identification & Auth Failures | ✅ | Strong JWT implementation |
| A08: Software & Data Integrity | ✅ | CSRF protection, input validation |
| A09: Security Logging & Monitoring | ✅ | Comprehensive logging system |
| A10: Server-Side Request Forgery | ✅ | Input validation, URL sanitization |

## Maintenance

### Regular Tasks

1. **Weekly**: Run security audit script
2. **Monthly**: Update dependencies
3. **Quarterly**: Review security headers and policies
4. **Annually**: Comprehensive security review

### Monitoring

- **Dependency Updates**: Automated notifications
- **Security Alerts**: Monitoring for new vulnerabilities
- **Incident Response**: Prepared procedures

## Contact

For security issues, please contact the security team immediately.

**Security Team**: security@presek.live
**Emergency**: +1 (555) 123-4567 (24/7)

## License

This security documentation is provided under the same license as the Presek application.

© 2026 Presek. All rights reserved.