import asyncio
import httpx
import feedparser
from database import db_manager as db

async def check_feed(client, name, url):
    try:
        resp = await client.get(url, timeout=15.0, follow_redirects=True)
        if resp.status_code != 200:
            return name, url, f"HTTP {resp.status_code}"
        
        feed = feedparser.parse(resp.content)
        if feed.bozo:
            # Bozo errors aren't always fatal, but useful to know
            return name, url, f"Bozo error: {feed.bozo_exception}"
        if not feed.entries:
            return name, url, "No entries found"
        return None
    except httpx.ConnectTimeout:
        return name, url, "Connection Timeout"
    except httpx.ConnectError:
        return name, url, "Connection Error"
    except Exception as e:
        return name, url, f"Error: {str(e)}"

async def main():
    sources = db.execute("SELECT name, url FROM sources WHERE is_active = TRUE")
    print(f"Checking {len(sources)} active feeds...")
    
    async with httpx.AsyncClient(headers={"User-Agent": "Presek/1.0 (Audit)"}) as client:
        # Check in batches of 10 to avoid overwhelming local resources/DNS
        batch_size = 10
        for i in range(0, len(sources), batch_size):
            batch = sources[i : i + batch_size]
            tasks = [check_feed(client, s['name'], s['url']) for s in batch]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r:
                    print(f"FAILED: {r[0]} ({r[1]}) - {r[2]}")
            # Small delay between batches
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
