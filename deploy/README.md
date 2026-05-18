# Presek Production Deployment

This directory contains scripts and configuration for deploying Presek to production environments.

## Deployment Options

### 1. Full Production Deployment (Recommended)

```bash
# On a fresh Ubuntu 22.04 server:
sudo bash deploy/production_deploy.sh
```

This script will:
- Install all dependencies (Python, PostgreSQL, Redis, Nginx)
- Set up system users and permissions
- Configure database and Redis
- Build the frontend
- Set up systemd services
- Configure SSL certificates
- Set up monitoring and logging

### 2. Manual Deployment Steps

If you prefer manual control:

```bash
# 1. Install dependencies
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql redis-server

# 2. Create user and directories
sudo useradd --system presek
sudo mkdir -p /opt/presek /var/log/presek /etc/presek
sudo chown -R presek:presek /opt/presek /var/log/presek

# 3. Copy application files
# (Copy your Presek code to /opt/presek)

# 4. Set up configuration
sudo cp deploy/production_config.example /etc/presek/environment
sudo chmod 640 /etc/presek/environment
sudo chown root:presek /etc/presek/environment

# 5. Edit configuration
sudo nano /etc/presek/environment

# 6. Set up Python environment
python3 -m venv /opt/presek/venv
source /opt/presek/venv/bin/activate
pip install -r requirements.txt

# 7. Build frontend
cd /opt/presek/web
npm install
npm run build

# 8. Set up services
sudo cp deploy/systemd/presek.service /etc/systemd/system/
sudo cp deploy/systemd/presek-worker.service /etc/systemd/system/
sudo cp deploy/systemd/presek-beat.service /etc/systemd/system/

# 9. Set up Nginx
sudo cp deploy/nginx/presek.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/presek.conf /etc/nginx/sites-enabled/

# 10. Start services
sudo systemctl daemon-reload
sudo systemctl enable presek presek-worker presek-beat nginx postgresql redis
sudo systemctl start presek presek-worker presek-beat nginx postgresql redis
```

## Configuration Files

### Main Configuration
- `/etc/presek/environment` - Main environment variables
- `/etc/presek/jwt_secret` - JWT secret key
- `/etc/presek/db_password` - Database password
- `/etc/presek/redis_password` - Redis password

### Service Configuration
- `/etc/systemd/system/presek.service` - Main API service
- `/etc/systemd/system/presek-worker.service` - Celery worker
- `/etc/systemd/system/presek-beat.service` - Celery beat (scheduled tasks)
- `/etc/nginx/sites-available/presek.conf` - Nginx configuration

## Security Configuration

### CSP (Content Security Policy)
The production deployment uses a strict CSP:
```
default-src 'self';
script-src 'self' 'nonce-{csp_nonce}';
style-src 'self' 'nonce-{csp_nonce}';
font-src 'self';
img-src 'self' data: blob:;
connect-src 'self' wss:;
frame-src 'none';
frame-ancestors 'none';
base-uri 'self';
form-action 'self';
object-src 'none';
media-src 'self' data:;
worker-src 'self' blob:
```

### Security Headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: no-referrer-when-downgrade`
- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`

## Monitoring and Maintenance

### Logs
- `/var/log/presek/presek.out.log` - API output
- `/var/log/presek/presek.err.log` - API errors
- `/var/log/presek/celery.out.log` - Celery worker output
- `/var/log/presek/celery.err.log` - Celery worker errors
- `/var/log/nginx/access.log` - Web access logs
- `/var/log/nginx/error.log` - Web server errors

### Backup and Restore

**Backup:**
```bash
sudo presek-backup
```

**Restore:**
```bash
sudo presek-restore /var/backups/presek/db_backup_20240101_120000.dump
```

### Monitoring Commands

**Check service status:**
```bash
sudo systemctl status presek presek-worker presek-beat nginx postgresql redis
```

**View logs:**
```bash
tail -f /var/log/presek/presek.out.log
tail -f /var/log/presek/presek.err.log
```

**Check API health:**
```bash
curl -s http://localhost:8000/api/health | jq .
```

## Scaling Options

### Database Read Replicas
Edit `/etc/presek/environment`:
```
USE_READ_REPLICA=true
DATABASE_READ_REPLICA_URL=postgresql://user:pass@replica-host:5432/presek
```

### Horizontal Scaling
For multiple API instances:
1. Set up a load balancer (Nginx, HAProxy)
2. Configure Redis session storage
3. Use shared storage for uploads
4. Configure database connection pooling

### GPU Acceleration
Edit `/etc/presek/environment`:
```
ENABLE_GPU_ACCELERATION=true
```
Requires CUDA and compatible GPU.

## Troubleshooting

### Common Issues

**API not starting:**
```bash
journalctl -u presek.service -f
```

**Database connection issues:**
```bash
sudo -u postgres psql -c "\l"
sudo -u postgres psql -d presek -c "\dt"
```

**Redis connection issues:**
```bash
redis-cli ping
redis-cli -a your_password ping
```

**Frontend not loading:**
```bash
ls -la /opt/presek/web/dist
sudo systemctl restart nginx
```

### Debugging Tips

1. **Check all service logs**
2. **Verify configuration files**
3. **Test database connections manually**
4. **Check network/firewall settings**
5. **Verify file permissions**

## Upgrade Process

1. **Backup current installation:**
   ```bash
   sudo presek-backup
   ```

2. **Stop services:**
   ```bash
   sudo systemctl stop presek presek-worker presek-beat
   ```

3. **Update code:**
   ```bash
   cd /opt/presek
   git pull origin main
   ```

4. **Update dependencies:**
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   cd web && npm install && npm run build
   ```

5. **Restart services:**
   ```bash
   sudo systemctl start presek presek-worker presek-beat
   ```

6. **Verify:**
   ```bash
   curl -s http://localhost:8000/api/health
   ```

## Security Best Practices

1. **Keep secrets secure** - Never commit configuration files to version control
2. **Regular updates** - Update dependencies monthly
3. **Monitor logs** - Set up log monitoring and alerts
4. **Backup regularly** - Automate daily backups
5. **Security patches** - Apply OS and software updates promptly
6. **Rate limiting** - Monitor and adjust as needed
7. **SSL certificates** - Renew automatically with certbot

## Support

For issues with production deployment:
1. Check logs first
2. Review configuration files
3. Test individual components
4. Consult the main README.md for application-specific details
