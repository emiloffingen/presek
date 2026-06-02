import asyncio
import logging
import os
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("capture_light_dark")

async def capture(browser, url, name, color_scheme, artifact_dir):
    context = await browser.new_context(
        viewport={"width": 1280, "height": 1200},
        color_scheme=color_scheme
    )
    page = await context.new_page()
    log.info(f"Capturing {name} ({color_scheme}) from {url}...")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        # Wait for fallback images or external requests to resolve
        await asyncio.sleep(6)
        path = os.path.join(artifact_dir, f"{name}.png")
        await page.screenshot(path=path, full_page=False)
        log.info(f"Saved to {path}")
    except Exception as e:
        log.error(f"Failed to capture {name}: {e}")
    finally:
        await context.close()

async def main():
    artifact_dir = "/home/emiloffingen/.gemini/antigravity-cli/brain/676f40f9-fce6-4961-8912-25f09be7d57e/screenshots"
    os.makedirs(artifact_dir, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Capture direct Astro local frontend port 3000
        await capture(browser, "http://localhost:3000", "homepage_light", "light", artifact_dir)
        await capture(browser, "http://localhost:3000", "homepage_dark", "dark", artifact_dir)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
