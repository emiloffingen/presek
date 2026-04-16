#!/bin/bash
set -e

# Run database initialization/migrations
echo "Checking database status..."
python3 -c "import config; from database import init_db; init_db()"

# Execute the CMD
echo "Starting service..."
exec "$@"
