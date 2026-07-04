#!/bin/bash
# Periodic task dispatcher (replacement for broken celery beat)
set -a
source /home/emiloffingen/presek/.env
set +a
cd /home/emiloffingen/presek

CELERY=".venv/bin/celery -A core.celery_app"
CYCLE=0

while true; do
    CYCLE=$((CYCLE + 1))
    echo "[$(date +%H:%M:%S)] Cycle $CYCLE"

    # Every cycle (10 min): ingestion
    $CELERY call tasks.ingestion_task.run_ingestion --queue=ingestion 2>/dev/null

    # Every cycle: auto-summarize
    $CELERY call tasks.intelligence.auto_summarize_task --queue=fast-track 2>/dev/null

    # Every cycle: prune queues
    $CELERY call tasks.maintenance.prune_intel_queue_task --queue=maintenance 2>/dev/null
    $CELERY call tasks.maintenance.prune_fast_track_queue_task --queue=maintenance 2>/dev/null
    $CELERY call tasks.maintenance.prune_maintenance_queue_task --queue=maintenance 2>/dev/null

    # Every cycle: catch-up syntheses
    $CELERY call tasks.maintenance.catch_up_cluster_syntheses_task --queue=maintenance 2>/dev/null
    $CELERY call tasks.maintenance.catch_up_recent_summaries_task --queue=maintenance 2>/dev/null

    # Every cycle: cluster management
    $CELERY call tasks.intelligence.recluster_recent_articles_task --queue=intel-heavy 2>/dev/null
    $CELERY call tasks.intelligence.repair_split_clusters_task --queue=intel-heavy 2>/dev/null
    
    # Every cycle: synthesis maintenance
    $CELERY call tasks.maintenance.check_fast_synthesis_upgrades_task --queue=maintenance 2>/dev/null

    # Every 3 cycles (30 min): KG refinement
    if [ $((CYCLE % 3)) -eq 0 ]; then
        $CELERY call tasks.intelligence.refine_knowledge_graph_sentiment_task --queue=intel-heavy 2>/dev/null
        echo "[$(date +%H:%M:%S)] KG refinement dispatched"
    fi

    # Every 6 cycles (1 hour): quality refresh
    if [ $((CYCLE % 6)) -eq 0 ]; then
        $CELERY call tasks.maintenance.refresh_synthesis_quality_task --queue=maintenance 2>/dev/null
        $CELERY call tasks.maintenance.refresh_low_score_syntheses_task --queue=maintenance 2>/dev/null
        echo "[$(date +%H:%M:%S)] Quality refresh dispatched"
    fi

    sleep 600
done
