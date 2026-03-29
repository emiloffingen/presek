import re
import datetime
import feedparser
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import clustering
from ai_engine import translate_to_macedonian
from categories import detect_category, detect_subcategory, detect_country
from config import (
    RSS_FEEDS, DIASPORA_FEEDS, HARDCODED_FEED_CATEGORIES,
    FEED_LIMIT, CLUSTER_LOOKBACK
)
from database import get_db

log = logging.getLogger("presek")

# Feed ETag / Last-Modified cache — avoids re-downloading unchanged feeds
_feed_etags:    dict[str, str] = {}
_feed_modified: dict[str, str] = {}
_etag_lock = threading.Lock()

# Circuit breaker: skip feeds with too many consecutive failures
_feed_failures: dict[str, int] = {}
_CIRCUIT_OPEN_THRESHOLD = 5

def normalize_headline(title: str) -> str:
    """Convert ALL-CAPS headlines to Title Case, leaving normally-cased text untouched."""
    if not title:
        return title
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 4:
        return title
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio > 0.75:
        return title.title()
    return title

def clean_rss_footer(text: str) -> str:
    """Remove common RSS 'signature' footers."""
    if not text:
        return ""
    import re as _re
    text = re.sub(r'The post\s+.*?\s+appeared first on\s+.*?(\.|$)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'This article was originally published on\s+.*?(\.|$)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Source:\s+https?://\S+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Source:\s+[A-Za-z0-9 ]+(\.|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Read more at\s+.*?(\.|$)', '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()

def _is_valid_image_url(url: str) -> bool:
    """Accept only plain http/https URLs of reasonable length."""
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        return False
    if len(url) < 12 or len(url) > 2000:
        return False
    return True

def fetch_feed(source, url):
    """Fetch a single RSS feed. Returns list of (title, link, desc, image_url) tuples."""
    # Circuit breaker: skip consistently failing feeds
    if _feed_failures.get(url, 0) >= _CIRCUIT_OPEN_THRESHOLD:
        log.debug(f"[circuit-open] Skipping {source} after {_CIRCUIT_OPEN_THRESHOLD} consecutive failures.")
        return source, [], None

    try:
        with _etag_lock:
            etag = _feed_etags.get(url)
            modified = _feed_modified.get(url)

        feed = feedparser.parse(
            url,
            etag=etag,
            modified=modified,
            request_headers={"User-Agent": "Presek.mk/1.0"},
        )
        if getattr(feed, "status", 200) == 304:
            _feed_failures[url] = 0
            return source, [], None

        with _etag_lock:
            if getattr(feed, "etag", None):
                _feed_etags[url] = feed.etag
            if getattr(feed, "modified", None):
                _feed_modified[url] = feed.modified
            
        entries = []
        for entry in feed.entries[:FEED_LIMIT]:
            title = normalize_headline(getattr(entry, "title", "").strip())
            link  = getattr(entry, "link",  "").strip()
            desc  = getattr(entry, "summary", "")

            # --- Image Extraction Logic ---
            image_url = ""
            if not image_url and hasattr(entry, 'media_content') and entry.media_content:
                for m in entry.media_content:
                    u = m.get('url', '')
                    if u and any(ext in u.lower() for ext in ['.jpg','.jpeg','.png','.webp','.gif']):
                        image_url = u; break
                if not image_url:
                    image_url = entry.media_content[0].get('url', '')
            if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
                for enc in entry.enclosures:
                    if 'image' in enc.get('type','') or any(ext in enc.get('url','').lower() for ext in ['.jpg','.jpeg','.png','.webp']):
                        image_url = enc.get('url',''); break
            if not image_url and hasattr(entry, 'links'):
                for link_obj in entry.links:
                    if 'image' in link_obj.get('type', ''):
                        image_url = link_obj.get('href', ''); break
            if not image_url and desc:
                import re as _re
                m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc, re.IGNORECASE)
                if m:
                    c = m.group(1)
                    if not any(s in c.lower() for s in ['pixel','icon','1x1','logo','gravatar','avatar']):
                        image_url = c
            if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get('url', '')
            # Validate image URL — reject data URIs, relative paths, oversized strings
            if not _is_valid_image_url(image_url):
                image_url = ""

            if title and link:
                entries.append((title, link, desc, image_url))

        _feed_failures[url] = 0  # reset on success
        return source, entries, None
    except Exception as e:
        _feed_failures[url] = _feed_failures.get(url, 0) + 1
        return source, [], str(e)

def ingest_feeds():
    """Fetch all RSS feeds in parallel, then write to DB sequentially."""
    conn = get_db()
    try:
        recent_rows = conn.execute(
            "SELECT title, cluster_id, created_at FROM articles ORDER BY created_at DESC LIMIT %s",
            (CLUSTER_LOOKBACK,)
        ).fetchall()
        recent_articles = [{"title": r["title"], "cluster_id": r["cluster_id"], "created_at": r["created_at"]} for r in recent_rows]

        all_entries = []  
        errors = []
        max_workers = min(len(RSS_FEEDS), 20)  
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_feed, s, u): s for s, u in RSS_FEEDS}
            for future in as_completed(futures):
                source, entries, error = future.result()
                if error:
                    errors.append(f"{source}: {error}")
                    log.warning(f"Feed error — {source}: {error}")
                else:
                    for title, link, desc, image_url in entries:
                        all_entries.append((source, title, link, desc, image_url))

        new_count = 0
        for source, title, link, desc, image_url in all_entries:
            try:
                if conn.execute("SELECT id FROM articles WHERE link = %s", (link,)).fetchone():
                    continue
                forced     = HARDCODED_FEED_CATEGORIES.get(source)
                category   = detect_category(title, description=desc, source=source, forced_category=forced)
                subcategory = detect_subcategory(title, description=desc) or ""
                cluster_id = clustering.find_or_create_cluster(title, recent_articles)
                now        = datetime.datetime.now()
                import re as _re
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                conn.execute(
                    "INSERT INTO articles (title, link, source, category, subcategory, cluster_id, created_at, image_url, description) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (title, link, source, category, subcategory, cluster_id, now, image_url, clean_desc)
                )
                recent_articles.insert(0, {"title": title, "cluster_id": cluster_id})
                if len(recent_articles) > CLUSTER_LOOKBACK:
                    recent_articles.pop()
                new_count += 1
            except Exception as e:
                log.error(f"DB write error — {source} | {title[:40]}: {e}")

        conn.commit()
        return new_count, errors
    finally:
        conn.close()

def ingest_diaspora_feeds():
    """Fetch diaspora RSS feeds and write to DB separately (without translation)."""
    conn = get_db()
    diaspora_recent = conn.execute(
        "SELECT title, cluster_id, created_at FROM articles WHERE country != '🇲🇰' ORDER BY created_at DESC LIMIT %s",
        (CLUSTER_LOOKBACK,)
    ).fetchall()
    diaspora_recent = [{"title": r["title"], "cluster_id": r["cluster_id"], "created_at": r["created_at"]} for r in diaspora_recent]
    conn.close()

    feed_meta = {s: (cat, detect_country(s)) for s, u, cat in DIASPORA_FEEDS}

    all_entries: list[tuple] = []
    errors: list[str] = []
    max_workers = min(len(DIASPORA_FEEDS), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_feed, s, u): s for s, u, _ in DIASPORA_FEEDS}
        for future in as_completed(futures):
            source, entries, error = future.result()
            if error:
                errors.append(f"{source}: {error}")
                log.warning(f"[diaspora] Feed error — {source}: {error}")
            else:
                cat, country = feed_meta[source]
                for title, link, desc, image_url in entries:
                    all_entries.append((source, title, link, desc, image_url, cat, country))

    if not all_entries:
        return 0, errors

    import re as _re
    conn = get_db()
    try:
        new_count = 0
        for i, (source, title, link, desc, image_url, category, country) in enumerate(all_entries):
            try:
                if conn.execute("SELECT id FROM articles WHERE link = %s", (link,)).fetchone():
                    continue
                
                display_title = normalize_headline(title)
                
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                cluster_id = clustering.find_or_create_cluster(display_title, diaspora_recent)
                now = datetime.datetime.now()

                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO articles "
                    "(title, original_title, link, source, category, subcategory, cluster_id, "
                    "created_at, image_url, description, original_description, country, is_translated) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (display_title, title, link, source, category, "", cluster_id,
                     now, image_url, clean_desc, clean_desc, country, 0)
                )
                article_id = cur.fetchone()[0]
                conn.commit()
                cur.close()

                # Dispatch background translation task
                from tasks import translate_article_task
                translate_article_task.delay(article_id, display_title, clean_desc)

                diaspora_recent.insert(0, {"title": display_title, "cluster_id": cluster_id})
                if len(diaspora_recent) > CLUSTER_LOOKBACK:
                    diaspora_recent.pop()
                new_count += 1
            except Exception as e:
                log.error(f"[diaspora] DB write error — {source} | {title[:40]}: {e}")

        conn.commit()
        return new_count, errors
    finally:
        conn.close()
