import logging
import asyncio
from celery_app import celery_app
from database import db_manager as db, prune_db
from image_service import image_service
from tasks.utils import log

@celery_app.task
def run_prune_db():
    """Standard maintenance."""
    try:
        prune_db()
    except Exception as e:
        log.error(f"[tasks] prune_db failed: {e}", exc_info=True)
    try:
        valid_rows = db.execute("SELECT DISTINCT cluster_id FROM articles")
        valid_ids = {str(r["cluster_id"]) for r in valid_rows if r["cluster_id"]}
        from ai_engine import cleanup_cover_art
        cleanup_cover_art(valid_ids)
    except Exception as e:
        log.error(f"[tasks] cleanup_cover_art failed: {e}", exc_info=True)

    try:
        # 3. Clean up orphaned local images and logs
        art_rows = db.execute("SELECT id FROM articles")
        active_art_ids = {int(r["id"]) for r in art_rows}
        loop = asyncio.get_event_loop()
        loop.run_until_complete(image_service.cleanup_storage(active_art_ids))
    except Exception as e:
        log.error(f"[tasks] cleanup_storage failed: {e}", exc_info=True)
