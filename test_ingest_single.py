import logging
import asyncio
from ingestion import fetch_feed_async, ingest_all_sources_async
from database import db_manager as db
import httpx

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_ingest")

async def test():
    source = db.execute_one("SELECT name, url, country, category, source_limit FROM sources WHERE name = 'Sitel'")
    source = dict(source)
    print(f"Testing source: {source['name']} ({source['url']})")
    
    async with httpx.AsyncClient(verify=True) as client:
        name, entries, err = await fetch_feed_async(client, source)
        if err:
            print(f"Error fetching: {err}")
            return
        
        print(f"Fetched {len(entries)} entries")
        for e in entries[:3]:
            print(f"  Title: {e.get('title')}")
            print(f"  Link: {e.get('link')}")

if __name__ == "__main__":
    asyncio.run(test())
