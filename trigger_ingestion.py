
from celery_app import celery_app
import time

def trigger():
    print("Triggering run_ingestion task...")
    result = celery_app.send_task('tasks.ingestion_task.run_ingestion')
    print(f"Task sent! ID: {result.id}")
    
    # Wait a bit to see if it starts
    print("Waiting 10 seconds for worker to pick it up...")
    time.sleep(10)
    print("Check logs: sudo journalctl -u presek-worker.service -f")

if __name__ == "__main__":
    trigger()
