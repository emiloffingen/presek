#!/bin/bash
# LEGACY: Full greenfield installer for /opt/presek (Gunicorn + Celery on :8000).
# The supported production path is the release runtime at ~/presek-runtime:
#   bootstrap_runtime_root.sh -> install_server.sh -> deploy_release.sh
# Do not use this script on an existing release-runtime server.
#
# Usage: sudo bash deploy/production_deploy.sh

set -eo pipefail

# Configuration
APP_NAME="presek"
DEPLOY_USER="presek"
DEPLOY_GROUP="presek"
INSTALL_DIR="/opt/presek"
LOG_DIR="/var/log/presek"
CONFIG_DIR="/etc/presek"
DATA_DIR="/var/lib/presek"
BACKUP_DIR="/var/backups/presek"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    exit 1
fi

# Create system user if not exists
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
    echo -e "${YELLOW}Creating system user...${NC}"
    useradd --system --shell /bin/false --home "$INSTALL_DIR" "$DEPLOY_USER"
fi

# Create required directories
echo -e "${YELLOW}Creating required directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$BACKUP_DIR"
mkdir -p "$INSTALL_DIR/uploads"
mkdir -p "$INSTALL_DIR/static"

# Set proper permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chown -R "$DEPLOY_USER:$DEPLOY_GROUP" "$INSTALL_DIR"
chown -R "$DEPLOY_USER:$DEPLOY_GROUP" "$LOG_DIR"
chown -R "$DEPLOY_USER:$DEPLOY_GROUP" "$DATA_DIR"
chmod -R 750 "$CONFIG_DIR"
chown -R root:"$DEPLOY_GROUP" "$CONFIG_DIR"

# Generate JWT secret if not exists
JWT_SECRET_FILE="$CONFIG_DIR/jwt_secret"
if [ ! -f "$JWT_SECRET_FILE" ]; then
    echo -e "${YELLOW}Generating JWT secret...${NC}"
    openssl rand -hex 32 > "$JWT_SECRET_FILE"
    chmod 640 "$JWT_SECRET_FILE"
    chown root:"$DEPLOY_GROUP" "$JWT_SECRET_FILE"
fi

# Generate database password if not exists
DB_PASSWORD_FILE="$CONFIG_DIR/db_password"
if [ ! -f "$DB_PASSWORD_FILE" ]; then
    echo -e "${YELLOW}Generating database password...${NC}"
    openssl rand -base64 24 > "$DB_PASSWORD_FILE"
    chmod 640 "$DB_PASSWORD_FILE"
    chown root:"$DEPLOY_GROUP" "$DB_PASSWORD_FILE"
fi

# Generate Redis password if not exists
REDIS_PASSWORD_FILE="$CONFIG_DIR/redis_password"
if [ ! -f "$REDIS_PASSWORD_FILE" ]; then
    echo -e "${YELLOW}Generating Redis password...${NC}"
    openssl rand -base64 24 > "$REDIS_PASSWORD_FILE"
    chmod 640 "$REDIS_PASSWORD_FILE"
    chown root:"$DEPLOY_GROUP" "$REDIS_PASSWORD_FILE"
fi

# Create environment file
echo -e "${YELLOW}Creating environment configuration...${NC}"
cat > "$CONFIG_DIR/environment" << EOF
# Presek Production Environment
ENV=production
LOG_LEVEL=INFO
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(cat "$JWT_SECRET_FILE")
DATABASE_URL=postgresql://presek:$(cat "$DB_PASSWORD_FILE")@localhost/presek
DATABASE_READ_REPLICA_URL=postgresql://presek:$(cat "$DB_PASSWORD_FILE")@localhost/presek_replica
REDIS_URL=redis://:$(cat "$REDIS_PASSWORD_FILE")@localhost:6379/0
PUBLIC_SITE_URL=https://presek.live
USE_READ_REPLICA=true
ENABLE_GPU_ACCELERATION=false
EOF

chmod 640 "$CONFIG_DIR/environment"
chown root:"$DEPLOY_GROUP" "$CONFIG_DIR/environment"

# Create systemd service
echo -e "${YELLOW}Creating systemd service...${NC}"
cat > /etc/systemd/system/presek.service << EOF
[Unit]
Description=Presek News Aggregation API
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
User=$DEPLOY_USER
Group=$DEPLOY_GROUP
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$CONFIG_DIR/environment
ExecStart=$INSTALL_DIR/venv/bin/python -m gunicorn --workers 4 --bind 0.0.0.0:8000 core.api_fast:app
Restart=always
RestartSec=5s
StandardOutput=append:$LOG_DIR/presek.out.log
StandardError=append:$LOG_DIR/presek.err.log

[Install]
WantedBy=multi-user.target
EOF

# Create nginx configuration
echo -e "${YELLOW}Creating nginx configuration...${NC}"
cat > /etc/nginx/sites-available/presek.conf << EOF
server {
    listen 80;
    server_name presek.live www.presek.live;

    # Redirect HTTP to HTTPS
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name presek.live www.presek.live;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/presek.live/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/presek.live/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1h;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'nonce-{csp_nonce}'; style-src 'self' 'nonce-{csp_nonce}'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self' wss:; frame-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; media-src 'self' data:; worker-src 'self' blob:" always;

    # Gzip Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Proxy settings
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # Static files
    location /static/ {
        alias $INSTALL_DIR/static/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }

    # Health check
    location /health {
        proxy_pass http://localhost:8000/api/health;
        access_log off;
    }

    # Error pages
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

# Enable nginx site
if [ ! -f /etc/nginx/sites-enabled/presek.conf ]; then
    ln -s /etc/nginx/sites-available/presek.conf /etc/nginx/sites-enabled/
fi

# Create logrotate configuration
echo -e "${YELLOW}Creating logrotate configuration...${NC}"
cat > /etc/logrotate.d/presek << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 $DEPLOY_USER $DEPLOY_GROUP
    sharedscripts
    postrotate
        systemctl reload nginx >/dev/null 2>&1 || true
    endscript
}
EOF

# Create backup script
echo -e "${YELLOW}Creating backup script...${NC}"
cat > /usr/local/bin/presek-backup << EOF
#!/bin/bash
# Presek Backup Script

BACKUP_DIR="$BACKUP_DIR"
CONFIG_DIR="$CONFIG_DIR"
DATE=\$(date +%Y%m%d_%H%M%S)
DB_USER="presek"
DB_NAME="presek"

# Database backup
pg_dump -U "\$DB_USER" -d "\$DB_NAME" -F c -f "\$BACKUP_DIR/db_backup_\$DATE.dump"

# Configuration backup
cp "\$CONFIG_DIR/environment" "\$BACKUP_DIR/config_backup_\$DATE.env"

# Clean up old backups (keep last 30 days)
find "\$BACKUP_DIR" -name "*.dump" -type f -mtime +30 -delete
find "\$BACKUP_DIR" -name "*.env" -type f -mtime +30 -delete

echo "Backup completed: \$BACKUP_DIR/db_backup_\$DATE.dump"
EOF

chmod +x /usr/local/bin/presek-backup

# Create restore script
echo -e "${YELLOW}Creating restore script...${NC}"
cat > /usr/local/bin/presek-restore << EOF
#!/bin/bash
# Presek Restore Script

DB_USER="presek"
DB_NAME="presek"

if [ \$# -eq 0 ]; then
    echo "Usage: \$0 <backup_file.dump>"
    exit 1
fi

BACKUP_FILE="\$1"

if [ ! -f "\$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: \$BACKUP_FILE"
    exit 1
fi

echo "Restoring database from \$BACKUP_FILE..."
pg_restore -U "\$DB_USER" -d "\$DB_NAME" -c "\$BACKUP_FILE"

echo "Restore completed successfully"
EOF

chmod +x /usr/local/bin/presek-restore

# Install dependencies
echo -e "${YELLOW}Installing system dependencies...${NC}"
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    postgresql \
    postgresql-contrib \
    redis-server \
    certbot \
    python3-certbot-nginx \
    logrotate \
    gunicorn

# Install pgvector extension
echo -e "${YELLOW}Installing pgvector extension...${NC}"
PG_VERSION=$(psql --version | grep -oE '[0-9]+' | head -n 1)
apt-get install -y "postgresql-${PG_VERSION}-pgvector"
systemctl restart postgresql

# Configure PostgreSQL
echo -e "${YELLOW}Configuring PostgreSQL...${NC}"
sudo -u postgres psql << 'EOF'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'presek') THEN
        CREATE USER presek WITH PASSWORD 'placeholder_password';
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'presek') THEN
        CREATE DATABASE presek OWNER presek;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'presek_replica') THEN
        CREATE DATABASE presek_replica OWNER presek;
    END IF;
END$$;

\c presek
CREATE EXTENSION IF NOT EXISTS vector;
EOF

# Set PostgreSQL user password
sudo -u postgres psql -c "ALTER USER presek WITH PASSWORD '$(cat "$DB_PASSWORD_FILE")';"

# Configure Redis
echo -e "${YELLOW}Configuring Redis...${NC}"
REDIS_PASS=$(cat "$REDIS_PASSWORD_FILE")
# Use a more robust method to set Redis password
cp /etc/redis/redis.conf /etc/redis/redis.conf.bak
awk -v pass="$REDIS_PASS" '
    /^#?[[:space:]]*requirepass[[:space:]]/ {
        print "requirepass " pass
        next
    }
    {print}
' /etc/redis/redis.conf.bak > /etc/redis/redis.conf
rm /etc/redis/redis.conf.bak
sed -i "s/^bind 127.0.0.1::1/bind 127.0.0.1 ::1/" /etc/redis/redis.conf

# Copy application files to installation directory
echo -e "${YELLOW}Copying application files...${NC}"
cp -r . "$INSTALL_DIR/"

# Set up Python virtual environment
echo -e "${YELLOW}Setting up Python environment...${NC}"
python3 -m venv "$INSTALL_DIR/venv"
cd "$INSTALL_DIR"
source "$INSTALL_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Install frontend dependencies
echo -e "${YELLOW}Building frontend...${NC}"
cd "$INSTALL_DIR/web" || exit 1
npm install
npm run build
cd "$INSTALL_DIR" || exit 1

# Set up Celery worker
echo -e "${YELLOW}Setting up Celery worker...${NC}"
cat > /etc/systemd/system/presek-worker.service << EOF
[Unit]
Description=Presek Celery Worker
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
User=$DEPLOY_USER
Group=$DEPLOY_GROUP
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$CONFIG_DIR/environment
ExecStart=$INSTALL_DIR/venv/bin/celery -A core.celery_app worker --loglevel=info
Restart=always
RestartSec=5s
StandardOutput=append:$LOG_DIR/celery.out.log
StandardError=append:$LOG_DIR/celery.err.log

[Install]
WantedBy=multi-user.target
EOF

# Set up Celery beat (for scheduled tasks)
cat > /etc/systemd/system/presek-beat.service << EOF
[Unit]
Description=Presek Celery Beat
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
User=$DEPLOY_USER
Group=$DEPLOY_GROUP
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$CONFIG_DIR/environment
ExecStart=$INSTALL_DIR/venv/bin/celery -A core.celery_app beat --loglevel=info
Restart=always
RestartSec=5s
StandardOutput=append:$LOG_DIR/celery-beat.out.log
StandardError=append:$LOG_DIR/celery-beat.err.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
echo -e "${YELLOW}Reloading systemd...${NC}"
systemctl daemon-reload

# Enable services
echo -e "${YELLOW}Enabling services...${NC}"
systemctl enable presek.service
systemctl enable presek-worker.service
systemctl enable presek-beat.service
systemctl enable nginx
systemctl enable postgresql
systemctl enable redis-server

# Start services
echo -e "${YELLOW}Starting services...${NC}"
systemctl start postgresql
systemctl start redis-server
systemctl start nginx
systemctl start presek.service
systemctl start presek-worker.service
systemctl start presek-beat.service

# Set up SSL certificates
echo -e "${YELLOW}Setting up SSL certificates...${NC}"
if [ ! -d "/etc/letsencrypt/live/presek.live" ]; then
    certbot --nginx -d presek.live -d www.presek.live --non-interactive --agree-tos --email admin@presek.live
fi

# Set up automatic certificate renewal
echo -e "${YELLOW}Setting up certificate renewal...${NC}"
cat > /etc/cron.d/presek-ssl-renewal << EOF
0 3 * * * root certbot renew --quiet --post-hook "systemctl reload nginx"
EOF

# Final verification
echo -e "${YELLOW}Verifying installation...${NC}"

# Check services
SERVICES=("presek.service" "presek-worker.service" "presek-beat.service" "nginx" "postgresql" "redis-server")
ALL_OK=true

for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo -e "${GREEN}✓ $service is running${NC}"
    else
        echo -e "${RED}✗ $service is not running${NC}"
        ALL_OK=false
    fi
done

# Check API health
if curl -s http://localhost:8000/api/health >/dev/null; then
    echo -e "${GREEN}✓ API is responding${NC}"
else
    echo -e "${RED}✗ API is not responding${NC}"
    ALL_OK=false
fi

# Check frontend
if [ -d "$INSTALL_DIR/web/dist" ]; then
    echo -e "${GREEN}✓ Frontend is built${NC}"
else
    echo -e "${RED}✗ Frontend is not built${NC}"
    ALL_OK=false
fi

if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}
========================================"
    echo "Presek deployment completed successfully!"
    echo "========================================"
    echo "API: https://presek.live/api"
    echo "Frontend: https://presek.live"
    echo "Admin: https://presek.live/admin"
    echo "Logs: $LOG_DIR"
    echo "Config: $CONFIG_DIR"
    echo "========================================${NC}"
else
    echo -e "${RED}
========================================"
    echo "Presek deployment completed with issues"
    echo "Please check the error messages above"
    echo "========================================${NC}"
    exit 1
fi
