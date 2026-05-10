from database import db_manager as db
from logging_config import get_logger

log = get_logger("presek_monitor")


def check_failed_tasks():
    try:
        rows = db.execute(
            "SELECT task_name, error_message, created_at FROM failed_tasks WHERE created_at > NOW() - INTERVAL '1 hour'"
        )
        if rows:
            log.warning(f"[monitor] Found {len(rows)} task failures in the last hour.")
            for row in rows:
                log.error(
                    f"[monitor] Task {row['task_name']} failed at {row['created_at']}: {row['error_message']}"
                )
        else:
            log.info("[monitor] No task failures detected in the last hour.")
    except Exception as e:
        log.error(f"[monitor] Error while checking failed tasks: {e}")


if __name__ == "__main__":
    check_failed_tasks()
