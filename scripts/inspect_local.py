import asyncio
import logging
import os

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("inspect_ui")

async def capture(browser, url, name):
    context = await browser.new_context(viewport={"width": 1280, "height": 3000})
    page = await context.new_page()
    log.info(f"Capturing {name} from {url}...")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await asyncio.sleep(5)
        path = f"screenshots/{name}.png"
        await page.screenshot(path=path, full_page=True)
        log.info(f"Saved to {path}")
    except Exception as e:
        log.error(f"Failed to capture {name}: {e}")
    finally:
        await context.close()

async def main():
    os.makedirs("screenshots", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        await capture(browser, "http://localhost:3000", "local_desktop")
        await capture(browser, "http://localhost:3000/mk", "local_mk_desktop")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
