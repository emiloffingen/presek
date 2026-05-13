#!/bin/bash
set -e

# Presek Migration Import Script
# This script extracts the migration bundle and restores the database on a new VPS.

echo "--- Starting Migration Import ---"

# 1. Check if the bundle exists
if [ ! -f "presek_migration.tar.gz" ]; then
    echo "Error: presek_migration.tar.gz not found in current directory."
    exit 1
fi

# 2. Extract files
echo "Extracting bundle into 'presek/' directory..."
mkdir -p presek
tar -xzvf presek_migration.tar.gz -C presek/
cd presek

# 3. Check for Docker
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    # Add current user to docker group if possible
    sudo usermod -aG docker $USER || true
    echo "Note: You might need to logout and login again if docker commands fail."
fi

# 4. Start Database and restore
echo "Starting Database container..."
docker compose up -d db

echo "Waiting for DB to be ready..."
# Give Postgres some time to initialize
MAX_RETRIES=30
COUNT=0
until docker compose exec db pg_isready -U presek > /dev/null 2>&1 || [ $COUNT -eq $MAX_RETRIES ]; do
  echo -n "."
  sleep 1
  ((COUNT++))
done
echo ""

if [ $COUNT -eq $MAX_RETRIES ]; then
    echo "Error: Database timed out during startup."
    exit 1
fi

echo "Restoring Database data..."
if [ -f "presek_db_backup.sql" ]; then
    cat presek_db_backup.sql | docker compose exec -T db psql -U presek -d presek
    echo "Database restoration complete."
else
    echo "Warning: presek_db_backup.sql not found. Skipping restore."
fi

# 5. Start everything
echo "Building and starting all services (this may take a few minutes)..."
docker compose up --build -d

echo ""
echo "--- SUCCESS ---"
echo "Migration complete! Containers are running."
echo ""
echo "Service Status:"
docker compose ps
