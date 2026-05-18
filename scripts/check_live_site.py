import asyncio
import logging
import os
import sys

from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("presek.check_live_site")


async def run():
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://presek.live/"
    log.info(f"Targeting URL: {target_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )
        page = await context.new_page()

        errors = []
        network_failures = []

        # Listen for console errors
        page.on(
            "console", lambda msg: errors.append(f"Console {msg.type}: {msg.text}") if msg.type == "error" else None
        )

        # Listen for page errors
        page.on("pageerror", lambda exc: errors.append(f"Page Error: {exc}"))

        # Listen for network failures
        def handle_response(response):
            if response.status >= 400:
                network_failures.append(f"Network Error: {response.url} returned {response.status}")

        page.on("response", handle_response)

        try:
            log.info(f"Navigating to {target_url} ...")
            response = await page.goto(target_url, wait_until="networkidle", timeout=60000)

            if not response:
                log.error("Failed to load page (no response)")
                return

            log.info(f"Page loaded with status {response.status}")

            if response.status != 200:
                log.error(f"Homepage returned status {response.status}")

            # 1. Scroll to ensure client:visible islands hydrate
            log.info("Scrolling page to hydrate widgets...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

            # Check for key elements and widgets
            elements_to_check = {
                "Branding/Logo": ".presek-branding, .presek-emblem-svg, .presek-logo-svg",
                "Navigation": "nav, .editorial-topbar",
                "Live Ticker": ".unified-ticker-track, .ticker-label",
                "News Articles": ".nyt-article, .cluster-card",
                "Newsletter Widget": "astro-island[component-url*='NewsletterIsland']",
                "National Mood Widget": "astro-island[component-url*='NationalMoodIsland']",
                "Topics in Focus": ".rail-tag-cloud",
                "Footer": "footer",
            }

            found_elements = {}
            for name, selector in elements_to_check.items():
                el = await page.query_selector(selector)
                found_elements[name] = "Found" if el else "NOT FOUND"
                if not el:
                    # Quote of the Day is optional if no good quotes are available
                    if name == "Quote of the Day":
                        log.warning("Quote of the Day not present (likely no suitable data for last 72h).")
                    else:
                        errors.append(f"Missing Element: {name}")

            # 2. Verify National Mood content after hydration
            mood_widget = await page.query_selector("astro-island[component-url*='NationalMoodIsland']")
            if mood_widget:
                text = await mood_widget.inner_text()
                if "Puls" in text or "Пулс" in text or "Mood" in text:
                    log.info("National Mood Widget: Functional and Hydrated.")
                else:
                    log.warning("National Mood Widget: Found but content seems limited. Check hydration.")

            # 3. Verify Live Ticker headlines
            ticker_headline = await page.query_selector(".live-ticker-headline")
            if ticker_headline:
                log.info(f"Live Ticker: Active with headline: {(await ticker_headline.inner_text())[:40]}...")
            else:
                log.warning("Live Ticker: Found but empty.")

            # 4. Final Assessment
            log.info("--- Final Elements Audit ---")
            for name, status in found_elements.items():
                log.info(f"{name}: {status}")

            # Take final screenshot
            os.makedirs("screenshots", exist_ok=True)
            domain = target_url.split("//")[-1].split("/")[0].replace(".", "_")
            await page.screenshot(path=f"screenshots/audit_{domain}.png", full_page=True)
            log.info(f"Final screenshot saved to screenshots/audit_{domain}.png")

        except Exception as e:
            log.exception(f"An error occurred during check: {e}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())


if __name__ == "__main__":
    asyncio.run(run())
