from core.database import db_manager as db

def check_failed_tasks():
    print("Recent failed tasks:")
    rows = db.execute("SELECT task_name, error_message, created_at FROM failed_tasks ORDER BY created_at DESC LIMIT 10")
    for r in rows:
        print(f"  {r['created_at']} | {r['task_name']} | {r['error_message']}")

if __name__ == "__main__":
    check_failed_tasks()
