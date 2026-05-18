#!/bin/bash
set -e

# Presek Systemd Migration Import Script
# This script installs system dependencies and sets up the app using systemd.

echo "--- Starting Systemd Migration Import ---"

# 1. Check if the bundle exists
if [ ! -f "presek_systemd_migration.tar.gz" ]; then
    echo "Error: presek_systemd_migration.tar.gz not found."
    exit 1
fi

# 2. Install System Dependencies (Debian/Ubuntu)
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y postgresql postgresql-contrib redis-server nginx python3-pip python3-venv curl tar git libpq-dev build-essential

# 3. Install 'uv' for fast python management
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env || true
fi

# 4. Setup Database
echo "Configuring PostgreSQL..."
# Note: This creates the user/db if they don't exist.
# You might need to set a password later in .env
sudo -u postgres psql -c "CREATE USER presek WITH SUPERUSER;" || true
sudo -u postgres psql -c "ALTER USER presek WITH PASSWORD 'presek';" || true
sudo -u postgres psql -c "CREATE DATABASE presek OWNER presek;" || true

# 5. Extract files
echo "Extracting bundle..."
mkdir -p ~/presek
tar -xzvf presek_systemd_migration.tar.gz -C ~/presek/
cd ~/presek

# 6. Bootstrap Runtime
echo "Bootstrapping runtime environment..."
# This script creates the venv and directory structure required by the systemd units
chmod +x deploy/bootstrap_runtime_root.sh
bash deploy/bootstrap_runtime_root.sh

# 7. Restore Database
echo "Restoring database data..."
if [ -f "presek_db_backup.sql" ]; then
    # Use the presek user we just created
    PGPASSWORD=presek psql -h localhost -U presek -d presek -f presek_db_backup.sql
    echo "Database restoration complete."
fi

# 8. Install Systemd Units and Nginx
echo "Installing systemd services and Nginx config..."
# This script installs files from deploy/systemd/ to /etc/systemd/system/
sudo bash deploy/install_server.sh

echo ""
echo "--- SUCCESS ---"
echo "Systemd migration complete!"
echo "Check status: sudo systemctl status presek.target"
echo "Note: If your username on this VPS is not 'emiloffingen', you may need to edit the .service files in /etc/systemd/system/"
