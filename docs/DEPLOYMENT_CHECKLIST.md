# Presek Deployment Checklist

This document provides a comprehensive checklist for deploying Presek in production.

## 📋 Pre-Deployment Checklist

### 1. Environment Variables
- [ ] `DATABASE_URL` - PostgreSQL connection string with credentials
- [ ] `REDIS_URL` - Redis connection string
- [ ] `SECRET_KEY` - Random secret key (>= 32 characters)
- [ ] `PRESEK_ADMIN_TOKEN` - Admin API token
- [ ] `GEMINI_API_KEY` - For Gemini AI (optional)
- [ ] `OPENAI_API_KEY` - For OpenAI (optional)
- [ ] `NTFY_TOPIC` - For notifications (optional)
- [ ] `NTFY_TOKEN` - For notifications (optional)
- [ ] `VAPID_PRIVATE_KEY` - Web Push private key
- [ ] `VAPID_PUBLIC_KEY` - Web Push public key
- [ ] `SMTP_HOST` - Email SMTP host
- [ ] `SMTP_PASS` - Email SMTP password
- [ ] `CLOUDFLARE_API_TOKEN` - For Cloudflare (optional)

### 2. Infrastructure Requirements
- [ ] PostgreSQL 15+ with pgvector extension
- [ ] Redis 7+
- [ ] Node.js 22+ (for frontend build)
- [ ] Python 3.12+
- [ ] Docker (for containerized deployment)
- [ ] nginx (for reverse proxy)

### 3. Database Setup
- [ ] Create `presek` database
- [ ] Create `presek` user with password
- [ ] Grant all privileges on database to user
- [ ] Enable pgvector extension: `CREATE EXTENSION vector;`
- [ ] Run migrations (if using alembic)

### 4. SSL/TLS Configuration
- [ ] SSL certificate for domain
- [ ] SSL key for domain
- [ ] Configure nginx with SSL
- [ ] Set up HTTP -> HTTPS redirect

## 🚀 Deployment Steps

### Option A: Manual Deployment

1. **Clone repository**
   ```bash
   git clone https://github.com/yourorg/presek.git
   cd presek
   ```

2. **Create .env file**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Set up Python virtualenv**
   ```bash
   python -m venv venv
   source venv/bin/activate
   uv sync
   ```

4. **Set up frontend**
   ```bash
   cd web
   npm install
   npm run build
   cd ..
   ```

5. **Run database migrations**
   ```bash
   # If using alembic
   alembic upgrade head
   ```

6. **Start services**
   ```bash
   # Using start.sh for development
   ./start.sh

   # Or manually:
   # FastAPI
   uvicorn api_fast:app --host 0.0.0.0 --port 8000 --workers 4

   # Celery worker
   celery -A celery_app worker --loglevel=info --concurrency=4

   # Celery beat
   celery -A celery_app beat --loglevel=info
   ```

### Option B: Production Deployment (Recommended)

1. **Set up runtime root**
   ```bash
   APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/bootstrap_runtime_root.sh
   ```

2. **Install server dependencies**
   ```bash
   sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=1 bash deploy/install_server.sh
   ```

3. **Deploy release**
   ```bash
   APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh
   ```

4. **Set up systemd services**
   ```bash
   # Copy systemd units
   sudo cp deploy/systemd/*.service /etc/systemd/system/
   sudo systemctl daemon-reload

   # Enable and start services
   sudo systemctl enable presek-fastapi.service
   sudo systemctl enable presek-worker.service
   sudo systemctl enable presek-beat.service
   sudo systemctl enable presek-astro.service

   sudo systemctl start presek-fastapi.service
   sudo systemctl start presek-worker.service
   sudo systemctl start presek-beat.service
   sudo systemctl start presek-astro.service
   ```

5. **Set up nginx**
   ```bash
   sudo cp deploy/nginx/presek.conf /etc/nginx/sites-available/presek
   sudo ln -s /etc/nginx/sites-available/presek /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

6. **Set up SSL (with Let's Encrypt)**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d presek.live -d www.presek.live
   ```

## 🔍 Post-Deployment Verification

### Health Checks
- [ ] `curl https://presek.live/api/health` returns healthy status
- [ ] Database connection is working
- [ ] Redis connection is working
- [ ] All services are running (`systemctl status presek-*`)

### Smoke Tests
- [ ] Homepage loads without errors
- [ ] News feed displays articles
- [ ] Search functionality works
- [ ] Cluster pages load
- [ ] Admin endpoints work (with auth token)

### Monitoring Setup
- [ ] Prometheus metrics endpoint accessible
- [ ] Logging is working (check log files)
- [ ] Error tracking configured

## 📊 Monitoring & Maintenance

### Log Files
- FastAPI: `/var/log/presek/fastapi.log`
- Worker: `/var/log/presek/worker.log`
- Beat: `/var/log/presek/beat.log`
- Astro: `/var/log/presek/astro.log`
- nginx: `/var/log/nginx/error.log`

### Monitoring Endpoints
- Health: `GET /api/health`
- Metrics: `GET /metrics`
- Version: `GET /api/version`

### Backup Strategy
- Database: Daily backups via `deploy/backup_postgres.sh`
- Logs: Rotated automatically
- Configuration: Version controlled in git

## 🔄 Update Process

1. **Pull latest changes**
   ```bash
   cd /home/emiloffingen/presek
   git pull origin main
   ```

2. **Deploy update**
   ```bash
   APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh
   ```

3. **Restart services**
   ```bash
   sudo systemctl restart presek-fastapi.service
   sudo systemctl restart presek-worker.service
   sudo systemctl restart presek-beat.service
   sudo systemctl restart presek-astro.service
   ```

4. **Verify deployment**
   ```bash
   curl https://presek.live/api/health
   curl https://presek.live/api/version
   ```

## 🛑 Rollback Process

1. **Identify previous release**
   ```bash
   ls -la /home/emiloffingen/presek-runtime/releases/
   ```

2. **Rollback to previous version**
   ```bash
   APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/rollback_release.sh <version>
   ```

3. **Restart services**
   ```bash
   sudo systemctl restart presek-*.service
   ```

## 📝 Configuration Reference

### Production Environment Variables
```bash
# Required
DATABASE_URL=postgresql://user:password@localhost/presek
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-very-long-random-secret-key-here

# Optional but recommended
ENV=production
PRESEK_ADMIN_TOKEN=your-admin-token
CORS_ORIGINS=https://presek.live,https://www.presek.live
LOG_LEVEL=INFO
LOG_FORMAT=json

# AI Providers
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=your-openai-api-key
LOCAL_TRANSLATION_ENABLED=true

# Notifications
NTFY_TOPIC=presek-prod
NTFY_TOKEN=your-ntfy-token
VAPID_PRIVATE_KEY=your-private-key
VAPID_PUBLIC_KEY=your-public-key

# Email
SMTP_HOST=smtp.example.com
SMTP_PASS=your-smtp-password
EMAIL_FROM="Presek <noreply@presek.live>"

# Performance tuning
DB_POOL_MINCONN=5
DB_POOL_MAXCONN=20
CLUSTER_LOOKBACK=300
AI_DAILY_LIMIT=10000

# OpenTelemetry (optional)
OTEL_ENABLED=true
OTEL_SERVICE_NAME=presek-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
```

### nginx Configuration Example
```nginx
server {
    listen 80;
    server_name presek.live www.presek.live;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name presek.live www.presek.live;

    ssl_certificate /etc/letsencrypt/live/presek.live/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/presek.live/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/emiloffingen/presek-runtime/current/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## 🆘 Troubleshooting

### Common Issues

**Issue: Database connection failed**
- Check `DATABASE_URL` is correct
- Verify PostgreSQL is running
- Check credentials in .env file
- Test connection: `psql -h localhost -U presek -d presek`

**Issue: Redis connection failed**
- Check `REDIS_URL` is correct
- Verify Redis is running
- Test connection: `redis-cli -u $REDIS_URL ping`

**Issue: Services won't start**
- Check logs: `journalctl -u presek-fastapi.service -f`
- Check environment variables are set
- Verify all dependencies are installed

**Issue: Frontend not building**
- Check Node.js version (requires 22+)
- Delete `node_modules` and reinstall: `rm -rf node_modules && npm install`
- Check for TypeScript errors: `npx tsc --noEmit`

**Issue: 502 Bad Gateway**
- Check nginx is running: `systemctl status nginx`
- Check backend services are running
- Check nginx error logs: `/var/log/nginx/error.log`

### Debug Commands

```bash
# Check all services
systemctl status presek-*.service

# View logs
journalctl -u presek-fastapi.service -n 100
journalctl -u presek-worker.service -n 100

# Test database connection
psql $DATABASE_URL -c "SELECT 1"

# Test Redis connection
redis-cli -u $REDIS_URL ping

# Check disk space
df -h

# Check memory usage
free -h

# Check open ports
ss -tulnp
```
