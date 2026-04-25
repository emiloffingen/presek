import asyncio
import sys
from playwright.async_api import async_playwright
import os

async def run(url, output):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(viewport={'width': 1280, 'height': 1600})
            print(f"Navigating to {url}...")
            await page.goto(url, wait_until='networkidle')
            await asyncio.sleep(2)
            await page.screenshot(path=output, full_page=True)
            print(f"Screenshot saved to {output}")
        finally:
            await browser.close()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 capture_specific.py <url> <output_path>")
        sys.exit(1)
    url = sys.argv[1]
    output = sys.argv[2]
    asyncio.run(run(url, output))
