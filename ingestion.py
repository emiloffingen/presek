import datetime
import feedparser
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import clustering
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
    text = _re.sub(r'The post\s+.*?\s+appeared first on\s+.*?(\.|$)', '', text, flags=_re.IGNORECASE | _re.DOTALL)
    text = _re.sub(r'This article was originally published on\s+.*?(\.|$)', '', text, flags=_re.IGNORECASE | _re.DOTALL)
    text = _re.sub(r'Source:\s+https?://\S+', '', text, flags=_re.IGNORECASE)
    text = _re.sub(r'Source:\s+[A-Za-z0-9 ]+(\.|$)', '', text, flags=_re.IGNORECASE)
    text = _re.sub(r'Read more at\s+.*?(\.|$)', '', text, flags=_re.IGNORECASE | _re.DOTALL)
    return text.strip()

def fetch_feed(source, url):
    """Fetch a single RSS feed. Returns list of (title, link, desc, image_url) tuples."""
    try:
        feed = feedparser.parse(
            url,
            etag=_feed_etags.get(url),
            modified=_feed_modified.get(url),
            request_headers={"User-Agent": "Presek.mk/1.0"},
        )
        if getattr(feed, "status", 200) == 304:
            return source, [], None
            
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
                m = _re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc, _re.IGNORECASE)
                if m:
                    c = m.group(1)
                    if not any(s in c.lower() for s in ['pixel','icon','1x1','logo','gravatar','avatar']):
                        image_url = c
            if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get('url', '')
            if image_url and (image_url.startswith('data:') or len(image_url) < 10):
                image_url = ""
            
            if title and link:
                entries.append((title, link, desc, image_url))
        return source, entries, None
    except Exception as e:
        return source, [], str(e)

def ingest_feeds():
    """Fetch all RSS feeds in parallel, then write to DB sequentially."""
    conn = get_db()
    try:
        recent_rows = conn.execute(
            "SELECT title, cluster_id FROM articles ORDER BY created_at DESC LIMIT ?",
            (CLUSTER_LOOKBACK,)
        ).fetchall()
        recent_articles = [{"title": r["title"], "cluster_id": r["cluster_id"]} for r in recent_rows]

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
                if conn.execute("SELECT id FROM articles WHERE link = ?", (link,)).fetchone():
                    continue
                forced     = HARDCODED_FEED_CATEGORIES.get(source)
                category   = detect_category(title, description=desc, source=source, forced_category=forced)
                subcategory = detect_subcategory(title, description=desc) or ""
                cluster_id = clustering.find_or_create_cluster(title, recent_articles)
                now        = datetime.datetime.now().isoformat()
                import re as _re
                clean_desc = _re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                conn.execute(
                    "INSERT INTO articles (title, link, source, category, subcategory, cluster_id, created_at, image_url, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        "SELECT title, cluster_id FROM articles WHERE country != '🇲🇰' ORDER BY created_at DESC LIMIT ?",
        (CLUSTER_LOOKBACK,)
    ).fetchall()
    diaspora_recent = [{"title": r["title"], "cluster_id": r["cluster_id"]} for r in diaspora_recent]
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
                if conn.execute("SELECT id FROM articles WHERE link = ?", (link,)).fetchone():
                    continue
                
                display_title = normalize_headline(title)
                cluster_id = clustering.find_or_create_cluster(display_title, diaspora_recent)
                now = datetime.datetime.now().isoformat()
                
                clean_desc = _re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]

                conn.execute(
                    "INSERT INTO articles "
                    "(title, original_title, link, source, category, subcategory, cluster_id, "
                    "created_at, image_url, description, country) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (display_title, title, link, source, category, "", cluster_id,
                     now, image_url, clean_desc, country)
                )
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
