import asyncio
import logging
import random
import re
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import trafilatura

from core.config import BOT_USER_AGENT
from core.http_pool import pooled_async_client
from core.text_extraction import clean_extracted_article_text
from utils import _peer_is_public, _resolve_public_ips

log = logging.getLogger("presek.crawler")

# robots.txt cache: origin -> (fetched_at, RobotFileParser | None)
_ROBOTS_CACHE: Dict[str, tuple] = {}
_ROBOTS_TTL_SECONDS = 3600.0


async def _robots_allows(url: str) -> bool:
    """Return True if robots.txt permits fetching ``url`` for our bot UA.

    Fails open (returns True) when robots.txt is missing, unreachable, or the
    SSRF guard rejects the robots.txt origin.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return True
    origin = f"{parts.scheme}://{parts.netloc}"
    now = time.time()
    cached = _ROBOTS_CACHE.get(origin)
    if cached and (now - cached[0]) < _ROBOTS_TTL_SECONDS:
        rp: Optional[RobotFileParser] = cached[1]
    else:
        rp = None
        try:
            robots_url = f"{origin}/robots.txt"
            _resolve_public_ips(robots_url)
            async with pooled_async_client("robots", timeout=10.0, follow_redirects=True) as client:
                async with client.stream("GET", robots_url, headers={"User-Agent": BOT_USER_AGENT}) as resp:
                    if not _peer_is_public(resp):
                        rp = None
                    elif resp.status_code == 200:
                        await resp.aread()
                        parser = RobotFileParser()
                        parser.set_url(robots_url)
                        parser.parse(resp.text.splitlines())
                        rp = parser
        except Exception as e:
            log.debug("robots.txt fetch failed for %s: %s", origin, e)
            rp = None
        _ROBOTS_CACHE[origin] = (now, rp)
    if rp is None:
        return True
    try:
        return rp.can_fetch(BOT_USER_AGENT, url)
    except Exception:
        return True


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
                        log.debug("Crawler fallback")

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
        # Content fetches use a browser UA: several MK outlets (e.g. ohridnews)
        # return 403 for unknown/polite bot UAs at the WAF level. robots.txt is
        # still evaluated against BOT_USER_AGENT in `_robots_allows`, so we stay
        # compliant while actually getting the HTML.
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "mk,en;q=0.8",
            "Referer": "https://presek.mk/",
        }

    async def extract_all(self, url: str) -> Dict[str, Any]:
        """
        Main entry point: Try fast extraction first, fall back to headless browser if needed.
        """
        await asyncio.sleep(random.uniform(0.5, 2.0))

        if not await _robots_allows(url):
            log.info("robots.txt disallows crawling %s", url)
            return {"url": url, "error": "blocked by robots.txt", "method": "fast"}

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
            _resolve_public_ips(url)
            async with pooled_async_client("crawler", timeout=15.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if not _peer_is_public(resp):
                        log.warning(f"SSRF blocked: peer not public for {url}")
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
            return {"url": url, "error": str(e), "method": "fast"}

        extracted = self._parse_with_trafilatura(html_content, final_url)
        content = extracted.get("content") or ""

        if len(content) < 200:
            # Middle fallback: jusText is local and token-free (already installed).
            # Keep whichever extractor yields more text; jusText can only help.
            justext_text = self._parse_with_justext(html_content) or ""
            if len(justext_text) > len(content):
                log.info(f"jusText improved {url} ({len(content)} -> {len(justext_text)} chars)")
                extracted["content"] = justext_text
                content = justext_text
                result["method"] = "fast-justext"

        result.update(extracted)
        if len(content) < 200:
            log.info(f"Low quality content for {url} ({len(content)} chars); returning as-is")
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
        # Boilerplate pruning is over-aggressive on some CMS layouts and can
        # return a short-but-plausible wrong block (e.g. telma.com.mk's cookie
        # consent banner extracts to ~235 chars, which clears the 200-char
        # gate and suppressed the old raw retry). Always extract the raw HTML
        # too and keep it when the pruned result is missing, tiny, or
        # materially shorter.
        raw_content = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if raw_content and (not content or len(content) < 200 or len(raw_content) > len(content) * 1.5):
            content = raw_content
        metadata = trafilatura.metadata.extract_metadata(html, default_url=url)

        return {
            "title": metadata.title if metadata else None,
            "content": clean_extracted_article_text(content) if content else None,
            "image_url": metadata.image if metadata else None,
            "author": metadata.author if metadata else None,
            "published_at": metadata.date if metadata else None,
        }

    @staticmethod
    def _parse_with_justext(html: str) -> str | None:
        """Boilerplate removal with jusText (Macedonian stoplist). Returns cleaned text or None."""
        try:
            import justext

            paragraphs = justext.justext(html, justext.get_stoplist("Macedonian"))
            text = "\n\n".join(p.text.strip() for p in paragraphs if not p.is_boilerplate and p.text.strip())
            return clean_extracted_article_text(text) if text else None
        except Exception as e:
            log.debug(f"jusText extraction failed: {e}")
            return None

    async def find_feeds(self, homepage_url: str) -> list[str]:
        """
        Visits a homepage and looks for RSS/Atom feed links.
        """
        log.info(f"Searching for feeds on {homepage_url}")
        feeds: list[str] = []
        try:
            _resolve_public_ips(homepage_url)
            async with pooled_async_client("crawler", timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(homepage_url, headers=self._get_headers())
                resp.raise_for_status()
                html = resp.text

            for tag in re.findall(
                r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>',
                html,
                re.IGNORECASE,
            ):
                href = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
                if href:
                    feeds.append(urljoin(homepage_url, href.group(1)))
            for href in re.findall(
                r'href=["\']([^"\']*(?:/feed|rss\.xml|feed\.xml)[^"\']*)["\']',
                html,
                re.IGNORECASE,
            ):
                feeds.append(urljoin(homepage_url, href))

            seen: set[str] = set()
            feeds = [f for f in feeds if not (f in seen or seen.add(f))]
        except Exception as e:
            log.error(f"Failed to find feeds on {homepage_url}: {e}")

        return feeds


# Singleton instance for easy access
crawler = CrawlerService()
