import asyncio
import logging
import os

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("inspect_ui")


async def capture(browser, url, name, is_mobile=False):
    view = {"width": 390, "height": 844} if is_mobile else {"width": 1280, "height": 1000}
    context = await browser.new_context(viewport=view, is_mobile=is_mobile)
    page = await context.new_page()
    log.info(f"Capturing {name} from {url}...")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await asyncio.sleep(5)  # Give it plenty of time for client-side rendering
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
        # MK Site
        await capture(browser, "https://presek.mk", "mk_mobile", is_mobile=True)
        await capture(browser, "https://presek.mk", "mk_desktop", is_mobile=False)
        # LIVE Site
        await capture(browser, "https://presek.live", "live_mobile", is_mobile=True)
        await capture(browser, "https://presek.live", "live_desktop", is_mobile=False)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
