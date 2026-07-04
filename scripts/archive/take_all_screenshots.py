import asyncio
import logging
import os
from urllib.parse import urljoin

from playwright.async_api import async_playwright

log = logging.getLogger("presek.take_all_screenshots")

PAGES = {
    "homepage": "/",
    "pregled": "/pregled",
    "briefing": "/briefing",
    "for_you": "/for-you",
    "pulse": "/pulse",
    "graf": "/graf",
    "izvori": "/izvori",
    "settings": "/settings",
    "about": "/about",
    "methodology": "/methodology",
    "marketing": "/marketing",
    "archive": "/archive"
}

async def capture_page(browser, base_url, path, name):
    url = urljoin(base_url, path)
    os.makedirs("screenshots", exist_ok=True)
    
    # 1. Capture Desktop View
    log.info(f"Capturing Desktop view for {name} ({url})...")
    desktop_page = await browser.new_page(viewport={"width": 1280, "height": 1600})
    try:
        await desktop_page.goto(url, wait_until="load", timeout=15000)
        await asyncio.sleep(4)
        # Capture standard viewport size screenshot
        await desktop_page.screenshot(path=f"screenshots/desktop_{name}.png", full_page=True)
        log.info(f"Desktop view for {name} saved.")
    except Exception as e:
        log.error(f"Failed to capture desktop view for {name}: {e}")
    finally:
        await desktop_page.close()

    # 2. Capture Mobile View
    log.info(f"Capturing Mobile view for {name} ({url})...")
    mobile_page = await browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        await mobile_page.goto(url, wait_until="load", timeout=15000)
        await asyncio.sleep(4)
        await mobile_page.screenshot(path=f"screenshots/mobile_{name}.png", full_page=True)
        log.info(f"Mobile view for {name} saved.")
    except Exception as e:
        log.error(f"Failed to capture mobile view for {name}: {e}")
    finally:
        await mobile_page.close()

async def run():
    base_url = "http://localhost:80"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            # Capture standard pages
            for name, path in PAGES.items():
                await capture_page(browser, base_url, path, name)
                
            # Extra: Find first cluster on homepage and capture its page
            log.info("Finding a cluster link on homepage...")
            temp_page = await browser.new_page(viewport={"width": 1280, "height": 1200})
            try:
                await temp_page.goto(base_url, wait_until="load", timeout=15000)
                await asyncio.sleep(3)
                first_cluster = await temp_page.query_selector('a[href^="/cluster/"]')
                if first_cluster:
                    href = await first_cluster.get_attribute("href")
                    log.info(f"Found cluster: {href}")
                    await capture_page(browser, base_url, href, "cluster_detail")
                else:
                    log.warning("No cluster link found on homepage.")
            except Exception as e:
                log.error(f"Failed to find or capture cluster detail page: {e}")
            finally:
                await temp_page.close()
                
        finally:
            await browser.close()
            
    log.info("All screenshots saved in screenshots/ directory.")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run())
