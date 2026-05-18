# Presek Security Verification Checklist

This checklist provides a comprehensive security verification process for the Presek application.

## 1. Infrastructure Security

### 1.1 Server Hardening
- [ ] Disable root SSH login
- [ ] Use SSH key authentication only
- [ ] Configure fail2ban for brute force protection
- [ ] Set up automatic security updates
- [ ] Configure firewall (ufw/iptables)
- [ ] Disable unused services
- [ ] Enable audit logging

### 1.2 Network Security
- [ ] Configure proper firewall rules
- [ ] Restrict database access to local/private network
- [ ] Restrict Redis access to local/private network
- [ ] Enable TLS for all external communications
- [ ] Configure proper DNS records (SPF, DKIM, DMARC)

## 2. Application Security

### 2.1 Authentication & Authorization
- [ ] Verify JWT secret is properly configured
- [ ] Test JWT token expiration
- [ ] Verify admin endpoints require authentication
- [ ] Test password hashing strength
- [ ] Verify session management

### 2.2 API Security
- [ ] Test rate limiting effectiveness
- [ ] Verify CSRF protection
- [ ] Test input validation
- [ ] Verify SQL injection protection
- [ ] Test XSS protection
- [ ] Verify CORS configuration

### 2.3 Security Headers
- [ ] Verify CSP headers are properly set
- [ ] Check HSTS configuration
- [ ] Verify X-Frame-Options
- [ ] Check X-Content-Type-Options
- [ ] Verify X-XSS-Protection
- [ ] Check Referrer-Policy

## 3. Data Security

### 3.1 Database Security
- [ ] Verify database encryption at rest
- [ ] Check database backup encryption
- [ ] Verify proper database user permissions
- [ ] Test database connection security
- [ ] Verify sensitive data encryption

### 3.2 Secrets Management
- [ ] Verify secrets are not in version control
- [ ] Check environment variable security
- [ ] Verify secret rotation procedures
- [ ] Test access to sensitive configuration files

## 4. Monitoring & Logging

### 4.1 Logging Configuration
- [ ] Verify comprehensive logging is enabled
- [ ] Check log rotation is configured
- [ ] Verify log retention policy
- [ ] Test log access controls

### 4.2 Monitoring Setup
- [ ] Verify Prometheus is monitoring all components
- [ ] Check Grafana dashboard accessibility
- [ ] Test alerting rules
- [ ] Verify monitoring of critical metrics

## 5. Dependency Security

### 5.1 Dependency Management
- [ ] Run `pip-audit` for Python vulnerabilities
- [ ] Run `npm audit` for JavaScript vulnerabilities
- [ ] Check for outdated dependencies
- [ ] Verify dependency pinning

### 5.2 Container Security
- [ ] Scan Docker images for vulnerabilities
- [ ] Verify minimal base images
- [ ] Check for proper user permissions in containers
- [ ] Test container runtime security

## 6. Compliance & Best Practices

### 6.1 Security Standards
- [ ] Verify OWASP Top 10 compliance
- [ ] Check CIS benchmark compliance
- [ ] Test against common vulnerability databases

### 6.2 Security Testing
- [ ] Perform penetration testing
- [ ] Conduct vulnerability scanning
- [ ] Test security headers
- [ ] Verify secure coding practices

## Security Verification Commands

### Infrastructure Checks
```bash
# Check SSH configuration
sudo sshd -T | grep -E "(PermitRootLogin|PasswordAuthentication|ChallengeResponseAuthentication)"

# Check firewall status
sudo ufw status verbose

# Check for security updates
sudo apt list --upgradable | grep -i security

# Check running services
systemctl list-units --type=service --state=running
```

### Application Checks
```bash
# Test JWT authentication
curl -v http://localhost:8000/admin/dashboard

# Test rate limiting
for i in {1..100}; do curl -s http://localhost:8000/api/news/recent > /dev/null; done

# Check security headers
curl -I http://localhost:8000/api/health

# Test SQL injection protection
curl -v "http://localhost:8000/api/news/search?q=' OR '1'='1"
```

### Database Checks
```bash
# Check PostgreSQL users and permissions
sudo -u postgres psql -c "\du"

# Check PostgreSQL connections
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity;"

# Test Redis security
redis-cli -a your_password ping
```

### Monitoring Checks
```bash
# Check Prometheus targets
curl -s http://localhost:9090/targets | jq .

# Check Grafana status
systemctl status grafana-server

# Test alerting
curl -X POST http://localhost:9090/api/v1/alerts -d '[{"labels":{"alertname":"TestAlert"},"annotations":{"description":"Test alert"}}]'
```

## Security Verification Tools

### Automated Scanning
```bash
# Install and run security scanning tools
sudo apt install lynis nikto sqlmap

# Run Lynis audit
sudo lynis audit system

# Run Nikto web scanner
nikto -h http://localhost

# Run SQLMap tests
sqlmap -u "http://localhost/api/news/search?q=test" --batch
```

### Dependency Scanning
```bash
# Python dependency scanning
pip install pip-audit safety
pip-audit
safety check

# JavaScript dependency scanning
cd web && npm install && npm audit
```

### Container Security
```bash
# Install and run container scanning
sudo apt install docker.io
sudo docker pull aquasec/trivy

# Scan Docker image
sudo docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image presek:latest
```

## Security Verification Report

After completing the security verification, create a report with:

1. **Findings Summary**: List of all security issues found
2. **Risk Assessment**: Severity rating for each issue
3. **Remediation Steps**: Specific actions to fix each issue
4. **Verification Results**: Test results and evidence
5. **Recommendations**: Long-term security improvements

## Continuous Security Monitoring

Set up ongoing security monitoring:

1. **Automated vulnerability scanning** (weekly)
2. **Dependency updates** (monthly)
3. **Security patch management** (automatic)
4. **Penetration testing** (quarterly)
5. **Security training** (annual)

## Emergency Response Plan

### Incident Response Procedures

1. **Detection**: Monitor for security incidents
2. **Containment**: Isolate affected systems
3. **Eradication**: Remove malicious code/access
4. **Recovery**: Restore from clean backups
5. **Post-incident**: Review and improve

### Backup and Recovery

- **Daily backups** with 30-day retention
- **Offsite backup storage**
- **Regular recovery testing**
- **Documented restore procedures**

## Security Contacts

- **Security Team**: security@presek.live
- **Incident Response**: +1-555-SECURE
- **Hosting Provider**: support@hosting.com
- **Domain Registrar**: support@registrar.com
