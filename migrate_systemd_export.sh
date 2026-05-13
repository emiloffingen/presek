#!/bin/bash
set -e

# Presek Systemd Migration Export Script
# This script packages the app for migration in a non-Docker (systemd) environment.

echo "--- Starting Systemd Migration Export ---"

# 1. Determine DB dump method
if docker compose ps db 2>/dev/null | grep -q "Up"; then
    echo "Detected Docker database. Dumping from container..."
    docker compose exec db pg_dump -U presek presek > presek_db_backup.sql
else
    echo "Detected local database. Dumping from system..."
    # This assumes the current user has access or uses .pgpass
    pg_dump -U presek -h localhost presek > presek_db_backup.sql || {
        echo "Local pg_dump failed. Trying as postgres user..."
        sudo -u postgres pg_dump presek > presek_db_backup.sql
    }
fi

# 2. Package everything
echo "Creating migration bundle (presek_systemd_migration.tar.gz)..."
# Exclude bulky/recreatable folders
tar -czvf presek_systemd_migration.tar.gz \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.cache' \
  --exclude='__pycache__' \
  --exclude='node_modules' \
  --exclude='*.tar.gz' \
  --exclude='presek-runtime/releases/*' \
  --exclude='presek-runtime/venv' \
  .

echo ""
echo "--- SUCCESS ---"
echo "Package created: presek_systemd_migration.tar.gz"
echo "Size: $(du -sh presek_systemd_migration.tar.gz | cut -f1)"
echo ""
echo "NEXT STEPS:"
echo "1. Copy this bundle and the import script to your new VPS:"
echo "   scp presek_systemd_migration.tar.gz migrate_systemd_import.sh user@NEW_VPS_IP:/home/user/"
echo "2. Log into the new VPS and run: bash migrate_systemd_import.sh"
