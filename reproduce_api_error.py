import asyncio
import datetime
import json

from core.database import db_manager as db


async def test():
    try:
        print("Fetching row...")
        row = await db.async_execute_one("SELECT * FROM daily_briefings ORDER BY date DESC LIMIT 1")
        if not row:
            print("No row found")
            return

        print(f"Date: {row['date']} ({type(row['date'])})")
        print(f"Metadata: {row.get('metadata')} ({type(row.get('metadata'))})")

        target_date = row["date"]

        # Test serialization
        data = {
            "status": "success",
            "date": target_date,
            "content": row["content"],
            "metadata": row.get("metadata") or {},
        }

        # This simulates what FastAPI does
        class DateEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                return super().default(obj)

        print("Testing JSON serialization...")
        json.dumps(data, cls=DateEncoder)
        print("Success!")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test())
