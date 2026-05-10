from __future__ import annotations

import re
import html
import datetime
import asyncio
import random
import feedparser
import logging
from collections import defaultdict
from typing import List, Dict, Any, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

try:
    import httpx
except ModuleNotFoundError:
    httpx = None

import clustering
from nlp.categories import (
    detect_category,
    detect_subcategory,
    normalize_headline,
    detect_topic,
)
from database import db_manager as db
from config import CLUSTER_LOOKBACK, HARDCODED_FEED_CATEGORIES, JUNK_KEYWORDS
from embeddings import generate_embeddings_batch
from health import record_source_fetch, get_source_statuses
from language import is_cyrillic_south_slavic
from api_helpers import is_safe_url

from prometheus_client import Counter

log = logging.getLogger("presek")

# --- Prometheus Metrics ---
INGESTION_TOTAL = Counter(
    "presek_ingestion_total", "Total articles fetched by source", ["source"]
)
INGESTION_ACCEPTED = Counter(
    "presek_ingestion_accepted_total", "Total articles accepted by source", ["source"]
)
INGESTION_ERRORS = Counter(
    "presek_ingestion_errors_total",
    "Total errors during ingestion",
    ["source", "error_type"],
)

_OG_IMAGE_READ_LIMIT = 64 * 1024
_OG_IMAGE_CONCURRENCY = 8
_BROWSER_LIKE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,mk;q=0.8",
}
_OG_IMAGE_SKIP_DOMAINS = {
    "fokus.mk",
}

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "ref_src",
}


def is_junk(title: str, desc: str) -> bool:
    """True if text contains blacklisted low-quality keywords or has clickbait patterns."""
    t_clean = str(title or "").strip()
    if not t_clean or len(t_clean) < 14:
        return True

    # Filter out titles that are just dates or numbers
    if re.match(r"^[\d\.\/\s:-]+$", t_clean):
        return True

    # Strip common prefixes for the junk check
    from nlp.categories import normalize_headline

    clean_title = normalize_headline(t_clean)

    text = f"{clean_title} {desc}".lower()
    if any(word in text for word in JUNK_KEYWORDS):
        return True

    # Filter out all-caps titles or long all-caps prefixes
    if clean_title:
        # Check if the title starts with an all-caps segment followed by a colon
        # We use a precise range for uppercase Cyrillic to avoid matching lowercase
        prefix_match = re.match(r"^([А-ЯЁЃЄЅІЇЈЉЊЋЌЍЎЏ\s]{8,}):", clean_title)
        if prefix_match:
            return True

        if len(clean_title) > 20 and clean_title.isupper():
            return True

    # Filter out minor police bulletin style news
    if any(
        phrase in text
        for phrase in [
            "приведен 27-годишњак",
            "приведено лице",
            "повреден скопјанец",
            "паднал од велосипед",
            "изгубил контрола",
            "мвр билтен",
            "дневно мени",
            "рецепт на денот",
            "курсна листа",
            "лото резултати",
        ]
    ):
        return True

    # 4. ML-based Quality Classifier (Local)
    try:
        from local_nlp import classify_news_quality_locally

        quality = classify_news_quality_locally(title, desc)
        if quality["score"] < 0.3:
            log.info(
                f"[ingestion] Rejecting low-quality content: {title[:50]}... (Score: {quality['score']}, Reason: {quality['reason']})"
            )
            return True
    except (ImportError, TypeError, ValueError, KeyError) as e:
        log.warning(f"[ingestion] Quality classifier configuration or data error: {e}")
    except Exception as e:
        log.error(
            f"[ingestion] Unexpected error in quality classifier: {e}", exc_info=True
        )

    return False


def detect_fact_check(source: str, title: str) -> bool:
    """Identify if an article is a fact-check."""
    if source.lower() == "vistinomer":
        return True

    fact_keywords = [
        "проверка на факти",
        "факти:",
        "неточно:",
        "дезинформација",
        "манипулација",
        "вистина или лага",
        "факт-чек",
        "факт чек",
        "fact-check",
        "fact check",
        "лажна вест",
        "лажни вести",
    ]
    lowered_title = title.lower()
    return any(kw in lowered_title for kw in fact_keywords)


def clean_rss_footer(text: str) -> str:
    """Removes common RSS footers and 'continue reading' artifacts."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"The post .* appeared first on .*", "", text)
    text = re.sub(r"Прочитајте повеќе на .*", "", text)
    text = re.sub(r"This article was originally published on .*", "", text)
    text = re.sub(r"Source: https?://.*", "", text)

    # Generic 'Read More' artifacts
    text = re.sub(r"Read More\s*»?\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Прочитај повеќе\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Continue reading\s*\.*$", "", text, flags=re.IGNORECASE)

    return text.strip()


def is_supported_display_language(title: str, description: str = "") -> bool:
    """Only ingest articles that can be displayed naturally without translation."""
    sample = f"{title or ''}. {description or ''}".strip()
    return is_cyrillic_south_slavic(sample)


def normalize_feed_link(link: str) -> str:
    """Canonicalize feed links by removing fragments and known tracking params."""
    if not link:
        return ""
    try:
        parts = urlsplit(link.strip())
        query_items = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        ]
        normalized_path = parts.path.rstrip("/") or "/"
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                normalized_path,
                urlencode(query_items),
                "",
            )
        )
    except (ValueError, TypeError, AttributeError) as e:
        log.debug(f"[ingestion] URL normalization failed: {e}")
        return link.strip()
    except Exception as e:
        log.error(
            f"[ingestion] Unexpected error in URL normalization: {e}", exc_info=True
        )
        return link.strip()


def canonical_hostname(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except (ValueError, TypeError, AttributeError) as e:
        log.debug(f"[ingestion] Hostname resolution failed for {url}: {e}")
        return ""
    except Exception as e:
        log.error(
            f"[ingestion] Unexpected error resolving hostname for {url}: {e}",
            exc_info=True,
        )
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_candidate_title(title: str) -> str:
    """Create a stable title fingerprint for same-source duplicate checks."""
    if not title:
        return ""
    text = normalize_headline(re.sub(r"<[^>]+>", " ", title))
    text = re.sub(
        r"^\[(live|update|breaking|video|photo)\]\s*", "", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"^(live|update|updated|breaking)\s*[:\-]\s*", "", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"\s*[\-–—|]\s*(live updates?|updated|video|photo|gallery)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b\d{1,2}:\d{2}\b", "", text)
    text = re.sub(r"\b(live|updates?|updated)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"[\"'“”‘’`]+", "", text)
    text = re.sub(r"[!?,.;:()\[\]{}]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_entry_timestamp(entry, fallback_now: datetime.datetime) -> datetime.datetime:
    """
    Extract a sane publication timestamp from an RSS entry.
    Falls back to the current cycle time when the feed timestamp is missing or implausible.
    """
    parsed_value = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
        or entry.get("created_parsed")
    )
    if parsed_value:
        try:
            published_at = datetime.datetime(*parsed_value[:6])
            if published_at > fallback_now + datetime.timedelta(minutes=30):
                return fallback_now
            if published_at < fallback_now - datetime.timedelta(days=14):
                return fallback_now
            return published_at
        except Exception as e:
            log.debug(f"Failed to parse published_at date: {e}")
    return fallback_now


def extract_image_url(entry):
    """Extracts the best representative image URL from an RSS entry."""

    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _image_url_score(
        url: str, mime_type: str, width: int, height: int, source_rank: float
    ) -> float:
        if not url or not re.match(
            r"^https?://", str(url).strip(), flags=re.IGNORECASE
        ):
            return -100.0

        parsed = urlsplit(str(url).strip())
        path = (parsed.path or "").lower()
        query = (parsed.query or "").lower()
        combined = f"{path}?{query}"
        mime = str(mime_type or "").lower()

        score = source_rank
        if "image/" in mime or path.endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".avif")
        ):
            score += 4.0
        elif "image" in mime:
            score += 3.0
        elif mime:
            score -= 4.0
        else:
            score += 1.0

        area = width * height
        if area:
            score += min(area / 160000.0, 6.0)
        if width >= 1200 or height >= 1200:
            score += 1.2
        elif width >= 600 or height >= 600:
            score += 0.8
        if width and width < 140:
            score -= 5.0
        if height and height < 140:
            score -= 5.0

        if any(
            pattern in combined
            for pattern in (
                "thumb",
                "thumbnail",
                "sprite",
                "logo",
                "icon",
                "avatar",
                "favicon",
                "pixel",
                "small",
                "ytimg",      # YouTube thumbnail indicator
                "video_thumb",
                "play_button",
                "player",
                "tiktok",     # General TikTok related image
            )
        ):
            score -= 6.0
        if any(
            pattern in combined
            for pattern in ("hero", "lead", "main", "large", "full", "original")
        ):
            score += 1.5

        return score

    candidates = []

    for item in (
        getattr(entry, "media_content", None) or entry.get("media_content", []) or []
    ):
        candidates.append(
            {
                "url": item.get("url") or item.get("href"),
                "mime": item.get("type") or item.get("medium"),
                "width": _to_int(item.get("width")),
                "height": _to_int(item.get("height")),
                "source_rank": 3.0,
            }
        )

    for item in getattr(entry, "links", None) or entry.get("links", []) or []:
        link_type = str(item.get("type") or "").lower()
        rel = str(item.get("rel") or "").lower()
        if "image" in link_type or rel == "enclosure":
            candidates.append(
                {
                    "url": item.get("href") or item.get("url"),
                    "mime": item.get("type"),
                    "width": _to_int(item.get("width")),
                    "height": _to_int(item.get("height")),
                    "source_rank": 2.0 if "image" in link_type else 1.4,
                }
            )

    for item in getattr(entry, "enclosures", None) or entry.get("enclosures", []) or []:
        candidates.append(
            {
                "url": item.get("url") or item.get("href"),
                "mime": item.get("type"),
                "width": _to_int(item.get("width")),
                "height": _to_int(item.get("height")),
                "source_rank": 1.0,
            }
        )

    # Extract <img> from summary/content HTML (many WP sites embed images this way)
    if not candidates:
        html_sources = []
        for content_block in (
            getattr(entry, "content", None) or entry.get("content", []) or []
        ):
            html_sources.append(content_block.get("value", ""))
        html_sources.append(
            getattr(entry, "summary", None) or entry.get("summary", "") or ""
        )
        html_sources.append(
            getattr(entry, "description", None) or entry.get("description", "") or ""
        )

        seen_urls = set()
        for html_source in html_sources:
            for img_match in re.finditer(
                r'<img[^>]+src=["\']([^"\']+)["\']', str(html_source)
            ):
                img_url = img_match.group(1).strip()
                if img_url in seen_urls or not re.match(r"^https?://", img_url):
                    continue
                seen_urls.add(img_url)
                # Extract width/height attributes if present
                w_match = re.search(r'width=["\']?(\d+)', img_match.group(0))
                h_match = re.search(r'height=["\']?(\d+)', img_match.group(0))
                candidates.append(
                    {
                        "url": img_url,
                        "mime": "image/",
                        "width": _to_int(w_match.group(1)) if w_match else 0,
                        "height": _to_int(h_match.group(1)) if h_match else 0,
                        "source_rank": 0.5,
                    }
                )

    best_url = None
    best_score = -100.0
    for candidate in candidates:
        score = _image_url_score(
            candidate["url"],
            candidate["mime"],
            candidate["width"],
            candidate["height"],
            candidate["source_rank"],
        )
        if score > best_score:
            best_score = score
            best_url = candidate["url"]

    return best_url


async def fetch_og_image(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch only the head of an article page and extract the og:image meta tag."""
    if not is_safe_url(url) and client.__class__.__module__.startswith("httpx"):
        return None

    try:
        async with client.stream(
            "GET", url, timeout=8.0, follow_redirects=True
        ) as resp:
            resp.raise_for_status()

            content_type = str(resp.headers.get("content-type", "")).lower()
            if (
                content_type
                and "html" not in content_type
                and "xml" not in content_type
            ):
                return None

            head_bytes = bytearray()
            async for chunk in resp.aiter_bytes():
                if not chunk:
                    continue

                remaining = _OG_IMAGE_READ_LIMIT - len(head_bytes)
                if remaining <= 0:
                    break

                head_bytes.extend(chunk[:remaining])

                # Check if we have enough to find the tag early
                if b"og:image" in head_bytes:
                    # We might have the full tag, or just the property name.
                    # If we can see a closing > after the property, we likely have it.
                    # To be safe, we decode what we have and check.
                    try:
                        temp_text = head_bytes.decode(
                            resp.encoding or "utf-8", errors="ignore"
                        )
                        if re.search(
                            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                            temp_text,
                            re.I,
                        ) or re.search(
                            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                            temp_text,
                            re.I,
                        ):
                            break
                    except Exception as e:
                        log.debug(f"OG image meta parse error: {e}")

                if len(head_bytes) >= _OG_IMAGE_READ_LIMIT:
                    break

            text = head_bytes.decode(resp.encoding or "utf-8", errors="ignore")
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            text,
            re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            text,
            re.IGNORECASE,
        )
        if m:
            img_url = m.group(1).strip()
            if img_url:
                resolved = urljoin(str(resp.url), img_url)
                if re.match(r"^https?://", resolved, flags=re.IGNORECASE):
                    return resolved
    except Exception as e:
        log.debug(f"Failed to extract og:image: {e}")
    return None


async def fill_missing_og_images(
    client: httpx.AsyncClient, candidates: List[Dict[str, Any]]
) -> int:
    """Backfill missing article images using og:image with bounded concurrency."""
    no_image = []
    skipped_domains = 0
    for candidate in candidates:
        if candidate["image_url"]:
            continue
        if canonical_hostname(candidate["link"]) in _OG_IMAGE_SKIP_DOMAINS:
            skipped_domains += 1
            continue
        no_image.append(candidate)
    if not no_image:
        return 0
    if skipped_domains:
        log.info(
            f"[ingest] Skipping og:image fetch for {skipped_domains} articles on bot-protected domains"
        )

    log.info(f"[ingest] Fetching og:image for {len(no_image)} articles without images")
    semaphore = asyncio.Semaphore(_OG_IMAGE_CONCURRENCY)

    async def _fetch(candidate: Dict[str, Any]) -> str | None:
        async with semaphore:
            return await fetch_og_image(client, candidate["link"])

    og_results = await asyncio.gather(*(_fetch(candidate) for candidate in no_image))
    filled = 0
    for candidate, og_url in zip(no_image, og_results):
        if og_url:
            candidate["image_url"] = og_url
            filled += 1
    if filled:
        log.info(f"[ingest] og:image filled {filled}/{len(no_image)} missing images")
    return filled


async def fetch_feed_async(
    client: httpx.AsyncClient, source: Dict[str, Any]
) -> Tuple[str, List[Any], str | None]:
    """Asynchronously fetch and parse a single RSS feed."""
    name = source["name"]
    url = source["url"]
    limit = source.get("source_limit", 10)

    try:
        resp = await client.get(url, timeout=15.0, follow_redirects=True)
        if (
            resp.status_code == 403
            and str(resp.headers.get("cf-mitigated", "")).lower() == "challenge"
        ):
            raise RuntimeError(f"Cloudflare challenge blocked feed: {url}")
        resp.raise_for_status()

        # Parse RSS in a thread pool since feedparser is blocking/CPU heavy
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, resp.content)

        entries = feed.entries[:limit]
        log.debug(f"[ingest] {name}: fetched {len(entries)} articles")
        return name, entries, None
    except Exception as e:
        log.warning(f"[ingest] {name} failed: {e}")
        return name, [], str(e)


def get_active_sources():
    """Fetches all active sources from the database."""
    rows = db.execute(
        "SELECT name, url, country, category, credibility, source_limit, pause_mode, pause_reason FROM sources WHERE is_active = TRUE"
    )
    return [dict(r) for r in rows]


def cosine_dist(a, b):
    """Calculates cosine distance between two vectors (lists of floats)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0


async def ingest_all_sources_async():
    """
    Modern Async Ingestion Pipeline.
    Uses httpx for concurrent fetching and asyncio for non-blocking orchestration.
    """
    sources = get_active_sources()
    if not sources:
        log.warning("No active sources found.")
        return 0, [], []
    if httpx is None:
        raise RuntimeError("httpx is required for feed ingestion")

    # 1. Duplicate detection setup
    known_links = set()
    recent_by_source = defaultdict(set)
    lookback_time = datetime.datetime.now() - datetime.timedelta(hours=12)

    with db.connection() as conn:
        # DatabaseManager/Wrapper execute already returns dicts or objects.
        from database import db_manager

        rows = db_manager.execute(
            "SELECT link, source, title FROM articles WHERE created_at >= %s",
            (lookback_time,),
        )
        for r in rows:
            known_links.add(normalize_feed_link(r["link"]))
            recent_by_source[r["source"]].add(normalize_candidate_title(r["title"]))

    # 2. Parallel Fetching with httpx
    candidates = []
    errors = []
    source_stats = {
        source["name"]: {"status": "ok", "fetched": 0, "accepted": 0, "error": ""}
        for source in sources
    }
    seen_links = set()
    seen_titles_by_source = defaultdict(set)
    cycle_now = datetime.datetime.now()

    headers = dict(_BROWSER_LIKE_HEADERS)
    headers["User-Agent"] += " Presek/6.0"

    async with httpx.AsyncClient(headers=headers, verify=True) as client:
        tasks = [fetch_feed_async(client, s) for s in sources]
        results = await asyncio.gather(*tasks)

        # Shuffle results to ensure we don't always process the same sources first if we hit the limit
        random.shuffle(results)

        from utils import redis_client

        for source_name, entries, err in results:
            if len(candidates) >= 80:
                break

            # Per-source lock to prevent concurrent processing of the same feed across workers
            lock_key = f"lock:ingest:source:{source_name}"
            try:
                if not redis_client.set(lock_key, "1", nx=True, ex=300):
                    log.info(
                        f"Source {source_name} is being processed by another worker, skipping."
                    )
                    continue
            except Exception as e:
                log.debug(f"Redis lock error for source {source_name}: {e}")
                continue

            try:
                source_stats[source_name]["fetched"] = len(entries)
                INGESTION_TOTAL.labels(source=source_name).inc(len(entries))
                if err:
                    source_stats[source_name]["status"] = "error"
                    source_stats[source_name]["error"] = str(err)
                    INGESTION_ERRORS.labels(
                        source=source_name, error_type=type(err).__name__
                    ).inc()
                    errors.append((source_name, err))
                    continue

                source_meta = next(s for s in sources if s["name"] == source_name)
                for e in entries:
                    if len(candidates) >= 80:
                        break

                    title = e.get("title", "").strip()
                    link = normalize_feed_link(e.get("link", ""))
                    title_key = normalize_candidate_title(title)

                    if (
                        not title
                        or not link
                        or link in known_links
                        or link in seen_links
                    ):
                        continue

                    raw_desc = e.get("summary", "") or e.get("description", "")
                    cleaned_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()

                    if not is_supported_display_language(title, cleaned_desc):
                        continue

                    if is_junk(title, cleaned_desc):
                        continue

                    if not title_key:
                        continue

                    if (
                        title_key in recent_by_source[source_name]
                        or title_key in seen_titles_by_source[source_name]
                    ):
                        continue

                    published_at = parse_entry_timestamp(e, fallback_now=cycle_now)

                    candidates.append(
                        {
                            "source": source_name,
                            "title": title,
                            "link": link,
                            "desc": cleaned_desc,
                            "image_url": extract_image_url(e),
                            "country": source_meta["country"],
                            "category": source_meta["category"],
                            "created_at": published_at,
                            "ingested_at": cycle_now,
                        }
                    )
                    seen_links.add(link)
                    seen_titles_by_source[source_name].add(title_key)
                    source_stats[source_name]["accepted"] += 1
                    INGESTION_ACCEPTED.labels(source=source_name).inc()
            finally:
                try:
                    redis_client.delete(lock_key)
                except Exception as e:
                    log.debug(f"Redis unlock error for source {source_name}: {e}")

            if (
                source_stats[source_name]["accepted"] == 0
                and source_stats[source_name]["fetched"] > 0
            ):
                source_stats[source_name]["status"] = "warning"

        await fill_missing_og_images(client, candidates)

    successful_sources = [
        name
        for name, stats in source_stats.items()
        if stats["fetched"] > 0 and not stats["error"]
    ]
    if successful_sources:
        db_manager.execute(
            "UPDATE sources SET last_fetched = NOW() WHERE name = ANY(%s)",
            (successful_sources,),
            fetch=False,
        )

    if not candidates:
        for source_name, stats in source_stats.items():
            record_source_fetch(
                source_name,
                stats["status"],
                fetched=stats["fetched"],
                accepted=stats["accepted"],
                error=stats["error"],
            )
        return 0, [], errors

    # 3. Batch Processing (CPU/API intensive parts)
    log.info(f"[ingestion] Processing {len(candidates)} candidates...")

    # Generate embeddings in one batch
    texts_to_embed = [f"{c['title']} {c['desc'][:200]}" for c in candidates]
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(
        None, generate_embeddings_batch, texts_to_embed
    )

    # 4. Clustering & DB Preparation
    # (Rest of the logic remains mostly same but wrapped in async orchestration)
    new_count = 0
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT title, cluster_id, created_at, category, topic FROM articles ORDER BY created_at DESC LIMIT %s",
            (CLUSTER_LOOKBACK,),
        )
        recent_articles = [dict(r) for r in cur.fetchall()]

        from clustering import (
            VECTOR_THRESHOLD,
            _cluster_title_overlap,
            _extract_title_entities,
        )

        prepared_rows = []
        batch_clusters = []

        for i, c in enumerate(candidates):
            try:
                emb = embeddings[i]
                forced = HARDCODED_FEED_CATEGORIES.get(c["source"])
                category = (
                    detect_category(
                        c["title"],
                        description=c["desc"],
                        source=c["source"],
                        forced_category=forced,
                    )
                    or c["category"]
                )
                subcategory = (
                    detect_subcategory(c["title"], description=c["desc"]) or ""
                )
                topic = detect_topic(c["title"], description=c["desc"])

                is_intl = c["country"] != "MK"
                # Always normalize headlines to strip ВИДЕО, ФОТО, etc.
                display_title = normalize_headline(c["title"])

                cluster_id = None
                if emb:
                    for bc in batch_clusters:
                        # Batch-time merges must be stricter than persisted clustering,
                        # especially for generic domestic news where adjacent stories
                        # often arrive together in the same fetch cycle.
                        if bc["category"] != category or bc["topic"] != topic:
                            continue
                        dist = cosine_dist(emb, bc["embedding"])
                        if dist >= (VECTOR_THRESHOLD * 0.78):
                            continue
                        if topic == "Вести" or not topic:
                            incoming_entities = _extract_title_entities(display_title)
                            batch_entities = bc.get("entities", set())
                            shared_entities = (
                                incoming_entities.intersection(batch_entities)
                                if incoming_entities and batch_entities
                                else set()
                            )
                            phrase_overlap = _cluster_title_overlap(
                                display_title, bc["title"]
                            )
                            if not shared_entities and phrase_overlap < 0.34:
                                continue
                            cluster_id = bc["cid"]
                            break

                if not cluster_id:
                    cluster_id = clustering.find_or_create_cluster(
                        conn,
                        display_title,
                        recent_articles,
                        embedding=emb,
                        category=category,
                        source=c["source"],
                        topic=topic,
                    )

                clean_desc = (
                    re.sub(r"<[^>]+>", "", c["desc"]).strip() if c["desc"] else ""
                )
                clean_desc = clean_rss_footer(clean_desc)[:500]
                created_at = c.get("created_at") or cycle_now
                ingested_at = c.get("ingested_at") or cycle_now
                is_fact = detect_fact_check(c["source"], c["title"])

                prepared_rows.append(
                    (
                        display_title,
                        c["title"] if is_intl else "",
                        c["link"],
                        c["source"],
                        category,
                        subcategory,
                        cluster_id,
                        created_at,
                        ingested_at,
                        c["image_url"],
                        clean_desc,
                        clean_desc if is_intl else "",
                        c["country"],
                        0,
                        str(emb) if emb else None,
                        topic,
                        is_fact,
                    )
                )

                if emb:
                    batch_clusters.append(
                        {
                            "cid": cluster_id,
                            "embedding": emb,
                            "category": category,
                            "topic": topic,
                            "title": display_title,
                            "entities": _extract_title_entities(display_title),
                        }
                    )
                recent_articles.insert(
                    0,
                    {
                        "title": display_title,
                        "cluster_id": cluster_id,
                        "created_at": created_at,
                        "category": category,
                        "topic": topic,
                    },
                )
                if len(recent_articles) > CLUSTER_LOOKBACK:
                    recent_articles.pop()

            except Exception as e:
                log.error(f"[ingest] error processing {c['source']}: {e}")

        # Batch Insert
        if prepared_rows:
            cur = conn.cursor()
            sql = """
                INSERT INTO articles (
                    title, original_title, link, source, category, subcategory, 
                    cluster_id, created_at, ingested_at, image_url, description, original_description, 
                    country, is_translated, embedding, topic, is_fact_check
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (link) DO NOTHING RETURNING id
            """
            cur.executemany(sql, prepared_rows, returning=True)
            
            inserted_ids = []
            while True:
                batch_results = cur.fetchall()
                if batch_results:
                    for r in batch_results:
                        if r and "id" in r:
                            inserted_ids.append(r["id"])
                if not cur.nextset():
                    break
            
            new_count = len(inserted_ids)
            conn.commit()

            # Post-ingestion tasks: batch trigger translations/summaries
            if inserted_ids:
                from utils import publish_event

                publish_event(
                    "updates",
                    {
                        "type": "new_articles_batch",
                        "count": len(inserted_ids),
                        "time": cycle_now,
                    },
                )

                inserted_data = db.execute(
                    "SELECT a.id, a.title, a.description, a.link, a.country, s.credibility, a.source, a.cluster_id FROM articles a JOIN sources s ON a.source = s.name WHERE a.id = ANY(%s)",
                    (inserted_ids,),
                )
                # Broadcast each non-junk article to the Live feed individually
                for art in inserted_data:
                    publish_event(
                        "updates",
                        {
                            "type": "new_article",
                            "title": art["title"],
                            "source": art["source"],
                            "cluster_id": art["cluster_id"],
                            "time": cycle_now,
                        },
                    )

                from tasks.ingestion_task import crawl_article_task
                from tasks.intelligence import (
                    summarize_articles_batch_task,
                    standardize_article_styles_batch_task,
                    detect_global_stories_batch_task,
                )

                # 1. Batch Crawl
                for art in inserted_data:
                    crawl_article_task.delay(art["id"], art["link"])

                # 2. Batch Global Story Detection
                detect_global_stories_batch_task.delay(inserted_ids)

                # 3. Batch Style Normalization
                credibility_ids = [
                    art["id"]
                    for art in inserted_data
                    if art.get("credibility", 1.5) < 1.2
                ]
                if credibility_ids:
                    standardize_article_styles_batch_task.delay(credibility_ids)

                # 4. Batch Summarization
                summarize_articles_batch_task.delay(inserted_ids)

    current_statuses = get_source_statuses()
    for source_name, stats in source_stats.items():
        record_source_fetch(
            source_name,
            stats["status"],
            fetched=stats["fetched"],
            accepted=stats["accepted"],
            error=stats["error"],
        )
        updated_status = (
            get_source_statuses().get(source_name)
            or current_statuses.get(source_name)
            or {}
        )
        if updated_status.get("should_auto_pause"):
            db.execute(
                """UPDATE sources
                   SET is_active = FALSE,
                       pause_mode = 'auto',
                       pause_reason = %s,
                       paused_at = NOW()
                   WHERE name = %s AND is_active = TRUE""",
                ("Repeated ingestion failures", source_name),
                fetch=False,
            )

    return new_count, inserted_ids, errors


def ingest_all_sources():
    """Synchronous wrapper for Celery/Script compatibility."""
    return asyncio.run(ingest_all_sources_async())


def ingest_feeds():
    return ingest_all_sources()
