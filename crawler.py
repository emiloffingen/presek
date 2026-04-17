import logging
import asyncio
import re
from typing import Dict, Any, Optional
from urllib.parse import urljoin

import httpx
import trafilatura
from playwright.async_api import async_playwright

from utils import _resolve_public_ips, _peer_ip

log = logging.getLogger("presek.crawler")

class CrawlerService:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,mk;q=0.8",
        }

    async def extract_all(self, url: str) -> Dict[str, Any]:
        """
        Main entry point: Try fast extraction first, fall back to headless browser if needed.
        """
        result = {
            "url": url,
            "title": None,
            "content": None,
            "image_url": None,
            "author": None,
            "published_at": None,
            "method": "fast"
        }

        # 1. Fast path: HTTPX + Trafilatura
        try:
            safe_ips = _resolve_public_ips(url)
            async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=10.0) as client:
                async with client.stream("GET", url) as resp:
                    p_ip = _peer_ip(resp)
                    if not p_ip or p_ip not in safe_ips:
                        log.warning(f"SSRF blocked: Peer IP {p_ip} not in safe list for {url}")
                        return await self._extract_headless(url)
                    
                    await resp.aread()
                    resp.raise_for_status()
                    html_content = resp.text
                    final_url = str(resp.url)
        except (ValueError, PermissionError) as e:
            log.warning(f"SSRF blocked for {url}: {e}")
            return {"url": url, "error": f"Security block: {e}"}
        except Exception as e:
            log.warning(f"Fast crawl failed for {url}: {e}")
            # If even the basic GET fails, we definitely want to try the "heavy" path
            return await self._extract_headless(url)

        # Use trafilatura on the fetched HTML
        extracted = self._parse_with_trafilatura(html_content, final_url)
        
        # If trafilatura failed to get meaningful content, it might be a JS-rendered site
        if not extracted.get("content") or len(extracted.get("content", "")) < 200:
            log.info(f"Low quality content from fast path for {url}, falling back to headless")
            return await self._extract_headless(url)

        result.update(extracted)
        return result

    def _parse_with_trafilatura(self, html: str, url: str) -> Dict[str, Any]:
        """Extracts content and metadata using trafilatura."""
        # trafilatura.extract is synchronous
        content = trafilatura.extract(
            html, 
            url=url, 
            include_comments=False, 
            include_tables=True,
            no_fallback=False
        )
        metadata = trafilatura.metadata.extract_metadata(html, default_url=url)
        
        return {
            "title": metadata.title if metadata else None,
            "content": content,
            "image_url": metadata.image if metadata else None,
            "author": metadata.author if metadata else None,
            "published_at": metadata.date if metadata else None,
        }

    async def _extract_headless(self, url: str) -> Dict[str, Any]:
        """
        Fallback path: Uses Playwright to render the page.
        Slow but extremely robust against modern JS frameworks.
        """
        log.info(f"Starting headless crawl for {url}")
        result = {"url": url, "method": "headless"}
        
        try:
            # SSRF Protection
            _resolve_public_ips(url)
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    # Set a common viewport and user agent
                    context = await browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent=self.headers["User-Agent"]
                    )
                    page = await context.new_page()
                    
                    # Wait for 'networkidle' to ensure JS has finished loading content
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    # Some sites might need a small extra sleep for hydration
                    await asyncio.sleep(1)
                    
                    html_content = await page.content()
                    final_url = page.url
                    
                    # Capture a screenshot as a fallback image if og:image is missing
                    screenshot_bytes = None
                    
                    # Extract metadata using page.evaluate to get computed properties
                    metadata = await page.evaluate("""() => {
                        const getMeta = (name) => {
                            const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
                            return el ? el.getAttribute('content') : null;
                        };
                        return {
                            title: document.title,
                            ogImage: getMeta('og:image'),
                            description: getMeta('og:description') || getMeta('description'),
                            author: getMeta('author') || getMeta('article:author'),
                        };
                    }""")
                finally:
                    await browser.close()

                # Still use trafilatura on the rendered HTML for the best text extraction
                extracted = self._parse_with_trafilatura(html_content, final_url)
                
                result.update({
                    "title": metadata.get("title") or extracted.get("title"),
                    "content": extracted.get("content"),
                    "image_url": metadata.get("ogImage") or extracted.get("image_url"),
                    "author": metadata.get("author") or extracted.get("author"),
                    "published_at": extracted.get("published_at")
                })
        except Exception as e:
            log.error(f"Headless crawl failed for {url}: {e}")
            result["error"] = str(e)

        return result

    async def find_feeds(self, homepage_url: str) -> list[str]:
        """
        Visits a homepage and looks for RSS/Atom feed links.
        """
        log.info(f"Searching for feeds on {homepage_url}")
        feeds = []
        try:
            # SSRF Protection
            _resolve_public_ips(homepage_url)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(user_agent=self.headers["User-Agent"])
                    # Increase timeout for potential redirects
                    await page.goto(homepage_url, wait_until="networkidle", timeout=30000)
                    
                    # Look for <link rel="alternate" type="application/rss+xml" ...>
                    found = await page.evaluate("""() => {
                        const links = Array.from(document.querySelectorAll('link[rel="alternate"]'));
                        return links
                            .filter(l => l.type && (l.type.includes('rss') || l.type.includes('atom') || l.type.includes('xml')))
                            .map(l => l.href);
                    }""")
                    
                    # Also look for <a> tags that look like feeds
                    found_links = await page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll('a'));
                        return anchors
                            .filter(a => a.href && (a.href.includes('/feed') || a.href.includes('rss.xml')))
                            .map(a => a.href);
                    }""")
                finally:
                    await browser.close()
                
                # Unique-ify and resolve relative URLs
                seen = set()
                all_raw = (found or []) + (found_links or [])
                for url in all_raw:
                    if not url: continue
                    resolved = urljoin(homepage_url, url)
                    if resolved not in seen:
                        feeds.append(resolved)
                        seen.add(resolved)
                        
        except Exception as e:
            log.error(f"Failed to find feeds on {homepage_url}: {e}")
            
        return feeds

# Singleton instance for easy access
crawler = CrawlerService()
