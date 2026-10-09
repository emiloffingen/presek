import asyncio
import logging
import os

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("inspect_ui")


async def capture(browser, url, name):
    context = await browser.new_context(viewport={"width": 1280, "height": 1600})
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
        await capture(browser, "http://127.0.0.1:3000/for-you", "local_for_you")
        await capture(browser, "http://127.0.0.1:3000/settings", "local_settings")
        await capture(browser, "http://127.0.0.1:3000/mk/for-you", "local_mk_for_you")
        await capture(browser, "http://127.0.0.1:3000/mk/settings", "local_mk_settings")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
