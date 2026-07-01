import asyncio
import logging
import os
import urllib.parse

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("capture_svg_directly")

async def capture(browser, url, name, artifact_dir):
    context = await browser.new_context(
        viewport={"width": 800, "height": 450}
    )
    page = await context.new_page()
    log.info(f"Capturing SVG directly from {url}...")
    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await asyncio.sleep(2)
        path = os.path.join(artifact_dir, f"{name}.png")
        await page.screenshot(path=path)
        log.info(f"Saved to {path}")
    except Exception as e:
        log.error(f"Failed to capture {name}: {e}")
    finally:
        await context.close()

async def main():
    artifact_dir = "/home/emiloffingen/.gemini/antigravity-cli/brain/676f40f9-fce6-4961-8912-25f09be7d57e/screenshots"
    os.makedirs(artifact_dir, exist_ok=True)
    
    title = "Na niškom aerodromu u maju 14 odsto više putnika nego u isto vreme prošle godine"
    params_light = urllib.parse.urlencode({"theme": "light", "cat": "Ekonomija", "t": title, "cid": "px123"})
    params_dark = urllib.parse.urlencode({"theme": "dark", "cat": "Ekonomija", "t": title, "cid": "px123"})
    
    url_light = f"http://localhost:5001/proxy?{params_light}"
    url_dark = f"http://localhost:5001/proxy?{params_dark}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        await capture(browser, url_light, "fallback_svg_light", artifact_dir)
        await capture(browser, "http://localhost:5001/proxy?cat=Ekonomija&theme=light&t=Test+Auto+System+Theme", "fallback_svg_auto_light", artifact_dir)
        await capture(browser, url_dark, "fallback_svg_dark", artifact_dir)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
