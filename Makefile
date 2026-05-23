# Makefile for Presek project maintenance

.PHONY: clean clean-db clean-cache clean-all seed fresh-start

# Default clean target
clean: clean-cache clean-logs

# Deep clean target for dev databases and untracked files
clean-all: clean-cache clean-logs
	@echo "Performing deep cleanup of untracked local DB and schedule files..."
	rm -f database.db presek.db presek.db-shm presek.db-wal presek.db.bak backfill.log celerybeat-schedule

# Remove all temporary logs, caches, and build artifacts
clean-cache:
	@echo "Cleaning application caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf .cache/*
	rm -rf web/dist/
	rm -rf .gemini/tmp/*

# Clear application logs
clean-logs:
	@echo "Cleaning application logs..."
	rm -rf logs/*

# Reset database (Requires psql access)
clean-db:
	@echo "WARNING: This will destroy all database data!"
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ]; then \
		psql -c "DROP DATABASE presek;" && \
		psql -c "CREATE DATABASE presek;" && \
		alembic upgrade head; \
	fi

# Seed source data
seed:
	@echo "Seeding sources..."
	python3 scripts/seed_sources.py
	python3 scripts/seed_feed_sources.py

# Full clean start
fresh-start: clean-cache clean-logs clean-db seed
	@echo "Environment reset successfully."
