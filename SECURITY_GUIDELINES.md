# 🔐 Presek Security Guidelines

## 📋 Overview

This document outlines security best practices and procedures for the Presek news aggregation platform.

## 🔒 Security Principles

### 1. Defense in Depth
- Multiple layers of security (network, application, data)
- Zero trust architecture for sensitive operations
- Regular security audits and penetration testing

### 2. Least Privilege
- Minimum necessary permissions for all services
- Role-based access control (RBAC)
- Regular permission reviews

### 3. Secure by Default
- Security enabled by default in all configurations
- Safe defaults for all security settings
- Fail-secure design patterns

## 🛡️ Application Security

### Authentication & Authorization

**JWT Implementation:**
- HS256 algorithm with strong secrets
- Short-lived tokens (60 minute expiry)
- Token revocation mechanism
- Secure storage in HttpOnly cookies

**Admin Access:**
```python
# Example secure admin endpoint
@router.get("/admin/stats")
async def admin_stats(admin: str = Depends(admin_auth)):
    # Only accessible with valid JWT token
    return get_admin_statistics()
```

### Input Validation

**Strict Validation:**
```python
# Example validation functions
def validate_cluster_id(cluster_id: str) -> str:
    if not CLUSTER_ID_PATTERN.match(cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
    return cluster_id
```

**Sanitization:**
```python
# HTML sanitization
def sanitize_html(text: str) -> str:
    return bleach.clean(text, tags=[], attributes={}, strip=True)
```

### Security Headers

**Comprehensive Header Protection:**
```python
# SecurityHeadersMiddleware implementation
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{csp_nonce}' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: https: blob:; "
    "connect-src 'self' https: wss:; "
    "frame-src 'self'; "
    "object-src 'none';"
)
```

## 🔐 Data Security

### Sensitive Data Handling

**Environment Variables:**
- Never commit `.env` files
- Use `.env.example` for documentation
- Validate all required variables on startup

**Database Security:**
- Parameterized queries (psycopg)
- Encrypted connections
- Regular backups
- Access logging

### Secrets Management

**Best Practices:**
- Use environment variables for secrets
- Rotate secrets regularly
- Never log secrets
- Use secret scanning tools

**Example `.env` structure:**
```env
# Required secrets
DATABASE_URL=postgresql://user:password@host/db
JWT_SECRET=strong_random_string_here
SECRET_KEY=another_strong_random_string

# API keys
OPENAI_API_KEY=sk-...
CLOUDFLARE_API_TOKEN=...

# Security settings
CSRF_TOKEN_SECRET=random_csrf_secret_here
```

## 🔧 Dependency Security

### Vulnerability Management

**Monthly Process:**
1. Run dependency scan: `pip-audit`
2. Review vulnerabilities
3. Update critical dependencies
4. Test updates thoroughly
5. Document changes

**Automated Scanning:**
```bash
# Manual scan
pip-audit --desc --format json

# Pre-commit hook (automated)
pre-commit run security-check
```

### Update Strategy

| Priority | Action | Timeframe |
|----------|--------|-----------|
| Critical | Immediate update | Within 24 hours |
| High | Scheduled update | Within 1 week |
| Medium | Next release | Within 2 weeks |
| Low | Backlog | Next major version |

## 🔍 Monitoring & Incident Response

### Security Monitoring

**Automated Checks:**
- Continuous security scanning in CI/CD
- Pre-commit hooks for secret detection
- Regular dependency audits

**Manual Reviews:**
- Quarterly security audits
- Annual penetration testing
- Code reviews with security focus

### Incident Response Plan

**Severity Levels:**
- **SEV-1**: Critical vulnerability, immediate action required
- **SEV-2**: High risk, action within 24 hours
- **SEV-3**: Medium risk, action within 72 hours
- **SEV-4**: Low risk, track and monitor

**Response Process:**
1. **Contain**: Isolate affected systems
2. **Assess**: Determine impact and root cause
3. **Communicate**: Notify stakeholders
4. **Remediate**: Apply fixes
5. **Review**: Post-incident analysis

## 📦 Deployment Security

### Infrastructure Security

**Production Requirements:**
- HTTPS with HSTS
- Firewall protection
- Regular patching
- Monitoring and alerting

**Container Security:**
- Minimal base images
- Non-root users
- Read-only filesystems
- Resource limits

### CI/CD Security

**Pipeline Protection:**
- Secret scanning in CI
- Signed commits
- Approval requirements for production
- Immutable artifacts

**Example CI security checks:**
```yaml
# GitHub Actions example
jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Secret scanning
        uses: gitleaks/gitleaks-action@v2
      - name: Dependency scanning
        run: pip-audit
      - name: Code quality
        run: ruff check .
```

## 🛠️ Developer Security Checklist

### Code Changes
- [ ] Validate all inputs
- [ ] Use parameterized queries
- [ ] Apply proper authentication
- [ ] Handle errors securely
- [ ] Log appropriately (no secrets)

### Dependencies
- [ ] Check for vulnerabilities
- [ ] Use pinned versions
- [ ] Review licenses
- [ ] Test updates thoroughly

### Deployment
- [ ] Verify configuration
- [ ] Test rollback procedure
- [ ] Monitor post-deployment
- [ ] Document changes

## 📚 Resources

### Tools
- **Static Analysis**: ruff, bandit, safety
- **Secret Scanning**: gitleaks, detect-secrets
- **Dependency Scanning**: pip-audit, dependabot
- **Monitoring**: Sentry, Prometheus

### Documentation
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security Best Practices](https://docs.python.org/3/howto/security.html)

### Emergency Contacts
- **Security Team**: security@presek.live
- **Incident Response**: +1-555-SECURE
- **Legal**: legal@presek.live

## 🔄 Maintenance

**Review Schedule:**
- Quarterly: Full security audit
- Monthly: Dependency updates
- Weekly: Security monitoring review
- Daily: Automated security checks

**Last Updated**: 2026-06-30
**Next Review**: 2026-09-30
**Owner**: Security Team