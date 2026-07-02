import asyncio
import logging
import random
from typing import Any, Dict
from urllib.parse import urljoin

import httpx
import trafilatura
from playwright.async_api import async_playwright

from core.text_extraction import clean_extracted_article_text
from utils import _peer_ip, _resolve_public_ips

log = logging.getLogger("presek.crawler")


def prune_boilerplate_html(html_str: str) -> str:
    """
    Remove non-article structures (header, footer, sidebars, related widgets, comment blocks, etc.)
    from the HTML tree using lxml before passing to Trafilatura.
    """
    if not html_str:
        return ""
    try:
        from lxml import html

        parser = html.HTMLParser(encoding="utf-8")
        doc = html.fromstring(html_str.encode("utf-8"), parser=parser)

        # 1. Elements to remove by tag name
        tags_to_remove = [
            "header",
            "footer",
            "nav",
            "aside",
            "script",
            "style",
            "noscript",
            "iframe",
            "form",
        ]
        for tag in tags_to_remove:
            for elem in doc.xpath(f"//{tag}"):
                if elem.getparent() is not None:
                    elem.getparent().remove(elem)

        noisy_keywords = [
            "sidebar",
            "side-bar",
            "widget",
            "comment",
            "related",
            "recommend",
            "share",
            "sharing",
            "social",
            "ads",
            "ad-box",
            "ad-container",
            "banner",
            "newsletter",
            "popup",
            "modal",
            "footer",
            "header",
            "nav-menu",
            "navbar",
            "menu-container",
            "tags",
            "tag-list",
            "meteo",
            "weather",
            "latest-news",
            "popular-news",
            "most-read",
            "most-popular",
            "disqus",
            "fb-root",
            "facebook",
            "cookie",
            "cookies",
            "consent",
            "gdpr",
            "privacy",
            # Regional (Serbian / Macedonian) keywords
            "povrzani",
            "povezani",
            "najnovi",
            "najcitanije",
            "najcitaniji",
            "najcitani",
            "reklama",
            "reklame",
            "spodeli",
            "podeli",
            "anketa",
            "komentari",
            "meteorološki",
            "kolačići",
            "kolacici",
            "privatnost",
        ]

        # Do not prune elements whose classes/IDs suggest they are main content wrappers
        exclude_wrapper_keywords = [
            "wrapper",
            "content",
            "main",
            "post",
            "article",
            "container",
            "body",
            "page",
        ]
        exclude_conds = []
        for exc in exclude_wrapper_keywords:
            exclude_conds.append(
                f"not(contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{exc}'))"
            )
            exclude_conds.append(
                f"not(contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{exc}'))"
            )
        exclude_xpath = " and ".join(exclude_conds)

        for keyword in noisy_keywords:
            xpath_query = (
                f"//*[self::div or self::section or self::ul or self::span or self::article or self::aside or self::td or self::tr]"
                f"[({exclude_xpath}) and (contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}') "
                f"or contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}'))]"
            )
            for elem in doc.xpath(xpath_query):
                if elem.tag not in ["body", "html"] and elem.getparent() is not None:
                    try:
                        elem.getparent().remove(elem)
                    except Exception:
                        pass

        return html.tostring(doc, encoding="utf-8").decode("utf-8")
    except Exception as e:
        log.warning(f"Failed to prune boilerplate HTML: {e}")
        return html_str


class CrawlerService:
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        ]

    def _get_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,mk;q=0.8",
            "Referer": "https://www.google.com/",
        }

    async def extract_all(self, url: str) -> Dict[str, Any]:
        """
        Main entry point: Try fast extraction first, fall back to headless browser if needed.
        """
        await asyncio.sleep(random.uniform(0.5, 2.0))

        result = {
            "url": url,
            "title": None,
            "content": None,
            "image_url": None,
            "author": None,
            "published_at": None,
            "method": "fast",
        }

        try:
            headers = self._get_headers()
            safe_ips = _resolve_public_ips(url)
            async with httpx.AsyncClient(
                headers=headers, follow_redirects=True, timeout=15.0
            ) as client:
                async with client.stream("GET", url) as resp:
                    p_ip = _peer_ip(resp)
                    if not p_ip or p_ip not in safe_ips:
                        log.warning(
                            f"SSRF blocked: Peer IP {p_ip} not in safe list for {url}"
                        )
                        return {
                            "url": url,
                            "error": "Security block: peer IP mismatch",
                            "method": "fast",
                        }

                    await resp.aread()
                    resp.raise_for_status()
                    html_content = resp.text
                    final_url = str(resp.url)
        except (ValueError, PermissionError) as e:
            log.warning(f"SSRF blocked for {url}: {e}")
            return {"url": url, "error": f"Security block: {e}"}
        except Exception as e:
            log.warning(f"Fast crawl failed for {url}: {e}")
            return await self._extract_headless(url)

        extracted = self._parse_with_trafilatura(html_content, final_url)

        if not extracted.get("content") or len(extracted.get("content", "")) < 200:
            log.info(
                f"Low quality content from fast path for {url}, falling back to headless"
            )
            return await self._extract_headless(url)

        result.update(extracted)
        return result

    def _parse_with_trafilatura(self, html: str, url: str) -> Dict[str, Any]:
        """Extracts content and metadata using trafilatura."""
        cleaned_html = prune_boilerplate_html(html)

        content = trafilatura.extract(
            cleaned_html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        metadata = trafilatura.metadata.extract_metadata(html, default_url=url)

        return {
            "title": metadata.title if metadata else None,
            "content": clean_extracted_article_text(content) if content else None,
            "image_url": metadata.image if metadata else None,
            "author": metadata.author if metadata else None,
            "published_at": metadata.date if metadata else None,
        }

    async def _extract_headless(self, url: str) -> Dict[str, Any]:
        """
        Fallback path: Uses Playwright to render the page.
        """
        log.info(f"Starting headless crawl for {url}")
        result = {"url": url, "method": "headless"}
        browser = None

        try:
            _resolve_public_ips(url)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                user_agent = random.choice(self.user_agents)
                context = await browser.new_context(
                    viewport={
                        "width": random.randint(1200, 1920),
                        "height": random.randint(800, 1080),
                    },
                    user_agent=user_agent,
                )
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(1)

                html_content = await page.content()
                final_url = page.url

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

                await browser.close()
                browser = None

                extracted = self._parse_with_trafilatura(html_content, final_url)

                result.update(
                    {
                        "title": (
                            str(metadata.get("title"))
                            if metadata.get("title")
                            else (
                                str(extracted.get("title"))
                                if extracted.get("title")
                                else None
                            )
                        ),
                        "content": (
                            str(extracted.get("content"))
                            if extracted.get("content")
                            else None
                        ),
                        "image_url": (
                            str(metadata.get("ogImage"))
                            if metadata.get("ogImage")
                            else (
                                str(extracted.get("image_url"))
                                if extracted.get("image_url")
                                else None
                            )
                        ),
                        "author": (
                            str(metadata.get("author"))
                            if metadata.get("author")
                            else (
                                str(extracted.get("author"))
                                if extracted.get("author")
                                else None
                            )
                        ),
                        "published_at": (
                            str(extracted.get("published_at"))
                            if extracted.get("published_at")
                            else None
                        ),
                    }
                )
        except Exception as e:
            log.error(f"Headless crawl failed for {url}: {e}")
            result["error"] = str(e)
        finally:
            if browser:
                await browser.close()

        return result

    async def find_feeds(self, homepage_url: str) -> list[str]:
        """
        Visits a homepage and looks for RSS/Atom feed links.
        """
        log.info(f"Searching for feeds on {homepage_url}")
        feeds = []
        try:
            _resolve_public_ips(homepage_url)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(
                        user_agent=self._get_headers()["User-Agent"]
                    )
                    await page.goto(
                        homepage_url, wait_until="networkidle", timeout=30000
                    )

                    found = await page.evaluate("""() => {
                        const links = Array.from(document.querySelectorAll('link[rel="alternate"]'));
                        return links
                            .filter(l => l.type && (l.type.includes('rss') || l.type.includes('atom') || l.type.includes('xml')))
                            .map(l => l.href);
                    }""")

                    found_links = await page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll('a'));
                        return anchors
                            .filter(a => a.href && (a.href.includes('/feed') || a.href.includes('rss.xml')))
                            .map(a => a.href);
                    }""")
                finally:
                    await browser.close()

                seen = set()
                all_raw = (found or []) + (found_links or [])
                for url in all_raw:
                    if not url:
                        continue
                    resolved = urljoin(homepage_url, url)
                    if resolved not in seen:
                        feeds.append(resolved)
                        seen.add(resolved)

        except Exception as e:
            log.error(f"Failed to find feeds on {homepage_url}: {e}")

        return feeds


# Singleton instance for easy access
crawler = CrawlerService()
