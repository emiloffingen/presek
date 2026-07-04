import logging
import time

from core.celery_app import celery_app

log = logging.getLogger("presek.trigger_ingestion")


def trigger():
    log.info("Triggering run_ingestion task...")
    result = celery_app.send_task("tasks.ingestion_task.run_ingestion")
    log.info(f"Task sent! ID: {result.id}")

    # Wait a bit to see if it starts
    log.info("Waiting 10 seconds for worker to pick it up...")
    time.sleep(10)
    log.info("Check logs: sudo journalctl -u presek-worker.service -f")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    trigger()
