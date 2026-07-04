import asyncio
import logging

import feedparser
import httpx

from core.database import db_manager as db
from core.ingestion import cleanup_rss_xml

log = logging.getLogger("presek.check_feeds")


async def check_feed(client, name, url):
    try:
        resp = await client.get(url, timeout=15.0, follow_redirects=True)
        if resp.status_code != 200:
            return name, url, f"HTTP {resp.status_code}"

        cleaned_content = cleanup_rss_xml(resp.content)
        feed = feedparser.parse(cleaned_content)
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    sources = db.execute("SELECT name, url FROM sources WHERE is_active = TRUE")
    log.info(f"Checking {len(sources)} active feeds...")

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    ) as client:
        # Check in batches of 10 to avoid overwhelming local resources/DNS
        batch_size = 10
        for i in range(0, len(sources), batch_size):
            batch = sources[i : i + batch_size]
            tasks = [check_feed(client, s["name"], s["url"]) for s in batch]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r:
                    log.warning(f"FAILED: {r[0]} ({r[1]}) - {r[2]}")
            # Small delay between batches
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
