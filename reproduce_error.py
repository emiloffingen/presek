import asyncio
from routes.stats import get_archive
from fastapi import HTTPException

async def test():
    try:
        # Mocking or using real DB if available in environment
        # The environment has DATABASE_URL set.
        res = await get_archive(date="2026-05-07", q="тест")
        print("Success!")
        from routes.stats import get_archive_daily_briefing
        brief = await get_archive_daily_briefing(date="2026-05-06")
        print("Briefing success!")
        print(f"Briefing: {brief['briefing'][:50]}...")
    except HTTPException as e:
        print(f"HTTP Error: {e.status_code} - {e.detail}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
