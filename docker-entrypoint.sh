#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database..."
python3 << END
import socket
import time
import os
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not set, skipping wait.")
    exit(0)

url = urlparse(db_url)
host = url.hostname
port = url.port or 5432

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("Database is up!")
            break
    except (socket.error, socket.timeout):
        print(f"Waiting for database at {host}:{port}...")
        time.sleep(1)
END

# Run database initialization/migrations
echo "Checking database status..."
python3 -c "import config; from database import init_db; init_db()"

# Execute the CMD
echo "Starting service..."
exec "$@"
