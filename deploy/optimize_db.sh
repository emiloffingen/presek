#!/bin/bash
# Presek 5.x Database Optimization Script
# Purpose: Maintain index performance and reclaim space as news articles accumulate.

DB_NAME="presek"
DB_USER="postgres"

echo "--- Database Optimization Started: $(date) ---"

# 1. Vacuum & Analyze (Reclaims space and updates statistics)
echo "> Running VACUUM ANALYZE on all tables..."
sudo -u $DB_USER psql -d $DB_NAME -c "VACUUM ANALYZE;"

# 2. Reindex critical news indexes (B-Tree indexes on dates get bloated fast)
echo "> Reindexing time-based and clustering indexes..."
sudo -u $DB_USER psql -d $DB_NAME -c "REINDEX INDEX CONCURRENTLY idx_created_at;"
sudo -u $DB_USER psql -d $DB_NAME -c "REINDEX INDEX CONCURRENTLY idx_ingested_at;"
sudo -u $DB_USER psql -d $DB_NAME -c "REINDEX INDEX CONCURRENTLY idx_cluster_id;"

# 3. Clean up stale entries if any (Safety check)
echo "> Cleaning up orphan cluster metadata..."
sudo -u $DB_USER psql -d $DB_NAME -c "DELETE FROM cluster_metadata WHERE cluster_id NOT IN (SELECT DISTINCT cluster_id FROM articles WHERE cluster_id IS NOT NULL);"

# 4. Check for index bloat (Summary report)
echo "> Current index sizes:"
sudo -u $DB_USER psql -d $DB_NAME -c "
SELECT relname as index_name, pg_size_pretty(pg_total_relation_size(relid)) as total_size
FROM pg_stat_user_tables 
ORDER BY pg_total_relation_size(relid) DESC 
LIMIT 10;"

echo "--- Database Optimization Complete: $(date) ---"
