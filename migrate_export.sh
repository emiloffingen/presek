#!/bin/bash
set -e

# Presek Migration Export Script
# This script dumps the database and packages the app for migration.

echo "--- Starting Migration Export ---"

# 1. Ensure we are in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "Error: docker-compose.yml not found. Please run this script from the project root."
    exit 1
fi

# 2. Check if containers are running
if ! docker compose ps db | grep -q "Up"; then
    echo "Error: Database container (db) is not running. Starting it..."
    docker compose up -d db
    sleep 3
fi

# 3. Dump the Database
echo "Dumping PostgreSQL database (presek)..."
docker compose exec db pg_dump -U presek presek > presek_db_backup.sql

# 4. Package everything
echo "Creating migration bundle (presek_migration.tar.gz)..."
# Exclude bulky/recreatable folders to keep the size manageable
tar -czvf presek_migration.tar.gz \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.cache' \
  --exclude='__pycache__' \
  --exclude='node_modules' \
  --exclude='*.tar.gz' \
  --exclude='presek_migration.tar.gz' \
  .

echo ""
echo "--- SUCCESS ---"
echo "Package created: presek_migration.tar.gz"
echo "Size: $(du -sh presek_migration.tar.gz | cut -f1)"
echo ""
echo "NEXT STEPS:"
echo "1. Copy this file to your new VPS:"
echo "   scp presek_migration.tar.gz user@NEW_VPS_IP:/home/user/"
echo "2. Copy 'migrate_import.sh' to your new VPS:"
echo "   scp migrate_import.sh user@NEW_VPS_IP:/home/user/"
echo "3. Log into the new VPS and run: bash migrate_import.sh"
