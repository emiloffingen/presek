import asyncio
from playwright.async_api import async_playwright
import os

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1280, 'height': 1600})
        
        # Ensure directory exists
        os.makedirs('screenshots', exist_ok=True)
        
        print("Capturing homepage...")
        await page.goto('https://presek.live', wait_until='load')
        # Wait a bit for images to proxy/load if needed
        await asyncio.sleep(4)
        await page.screenshot(path='screenshots/homepage_desktop.png', full_page=True)
        
        # Capture mobile version
        print("Capturing homepage mobile...")
        mobile_page = await browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
        await mobile_page.goto('https://presek.live', wait_until='load')
        await asyncio.sleep(4)
        await mobile_page.screenshot(path='screenshots/homepage_mobile.png', full_page=True)
        
        # Find first cluster and capture it
        print("Capturing a cluster page...")
        first_cluster = await page.query_selector('a[href^="/cluster/"]')
        if first_cluster:
            href = await first_cluster.get_attribute('href')
            cluster_url = f"https://presek.live{href}"
            await page.goto(cluster_url, wait_until='load')
            await asyncio.sleep(4)
            await page.screenshot(path='screenshots/cluster_detail.png', full_page=True)
        
        await browser.close()
        print("Screenshots saved in screenshots/ directory.")

if __name__ == '__main__':
    asyncio.run(run())
