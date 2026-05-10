# Presek Backup Configuration

## Overview

This document describes the backup strategy for Presek's PostgreSQL database and critical files.

## Backup Script

The main backup script is located at `deploy/backup_postgres.sh`. It performs:

- **Encrypted or uncompressed** PostgreSQL dumps using `pg_dump`
- **Automatic pruning** of backups older than 7 days (configurable)
- **Logging** to track backup operations

## Setup

### 1. Configure Environment

Set the following environment variables in your `.env` file or system environment:

```bash
# Required
DATABASE_URL=postgresql://user:password@host:port/database

# Optional
BACKUP_PASSPHRASE=your_strong_passphrase_here  # For encrypted backups
BACKUP_DIR=/path/to/backups  # Default: $APP_ROOT/shared/backups
KEEP_DAYS=7  # Number of days to retain backups
REQUIRE_BACKUP_ENCRYPTION=1  # Fail if BACKUP_PASSPHRASE not set
```

### 2. Test Backup Script

Run a test backup manually:

```bash
# Make executable if not already
chmod +x deploy/backup_postgres.sh

# Run test backup
APP_ROOT=/path/to/presek ./deploy/backup_postgres.sh
```

### 3. Set Up Cron Job

Install the provided crontab file:

```bash
# Copy to system crontab (run as the same user that runs the app)
crontab deploy/crontab

# Or add manually to root crontab
crontab -e
# Paste contents of deploy/crontab
```

The default schedule:
- **Daily backup**: 2:00 AM every day
- **Log rotation**: Weekly (Sunday 3:00 AM)
- **Health check**: Daily at 3:00 AM

### 4. Verify Backup Directory

Ensure the backup directory exists and is writable:

```bash
BACKUP_DIR=/home/emiloffingen/presek-runtime/shared/backups
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
```

## Backup Files

Backups are stored with the naming pattern:

- **Unencrypted**: `presek-YYYYMMDDTHHMMSSZ.sql.gz`
- **Encrypted**: `presek-YYYYMMDDTHHMMSSZ.sql.gz.gpg`

Example: `presek-20240515T020000Z.sql.gz.gpg`

## Restore Instructions

### From Encrypted Backup

```bash
# List available backups
ls -la /path/to/backups/

# Restore (replace with your passphrase and file)
gpg --decrypt --passphrase "your_passphrase" -o restored.sql.gz \
  /path/to/backups/presek-20240515T020000Z.sql.gz.gpg
gunzip restored.sql.gz
psql $DATABASE_URL < restored.sql
```

### From Unencrypted Backup

```bash
gunzip -c /path/to/backups/presek-20240515T020000Z.sql.gz | psql $DATABASE_URL
```

## Monitoring

Backup logs are written to:

- **Script output**: `$BACKUP_DIR/../backup.log` (or stdout if not configured)
- **Cron logs**: Typically `/var/log/syslog` or `/var/log/cron`

Check logs with:

```bash
# View recent backup logs
tail -n 50 /home/emiloffingen/presek/logs/backup.log

# Check cron execution
grep backup /var/log/syslog
```

## Security Considerations

1. **Encryption**: Always use `BACKUP_PASSPHRASE` for production backups
2. **Permissions**: Restrict backup directory to app user only
3. **Offsite**: Consider copying backups to offsite storage (S3, R2, etc.)
4. **Rotation**: Test restore process periodically

## Offsite Backup (Optional)

Add this to your crontab to sync backups to Cloudflare R2 or S3:

```bash
# Sync to R2/S3 30 minutes after local backup
30 2 * * * rclone sync /path/to/backups/ r2:presek-backups/ >> /home/emiloffingen/presek/logs/backup_sync.log 2>&1
```

## Disaster Recovery

In case of complete server loss:

1. Provision new server
2. Install PostgreSQL
3. Create database and user
4. Restore from latest backup
5. Verify data integrity
6. Start application

## Testing Backups

Test your backups monthly:

```bash
# Pick a recent backup
LATEST_BACKUP=$(ls -t /path/to/backups/presek-*.sql.gz* | head -1)

# Test restore to a temporary database
createdb presek_test_restore
pg_restore --clean --if-exists --dbname presek_test_restore "$LATEST_BACKUP"

# Verify
echo "SELECT count(*) FROM articles;" | psql presek_test_restore

# Clean up
dropdb presek_test_restore
```
