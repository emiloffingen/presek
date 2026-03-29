import re
import datetime
import feedparser
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import clustering
from ai_engine import translate_to_macedonian
from categories import detect_category, detect_subcategory, detect_country, normalize_headline
from database import get_db
from config import RSS_FEEDS, DIASPORA_FEEDS, FEED_LIMIT, CLUSTER_LOOKBACK, HARDCODED_FEED_CATEGORIES

log = logging.getLogger("presek")

def clean_rss_footer(text: str) -> str:
    """Removes common RSS footers like 'The post ... appeared first on ...'"""
    if not text: return ""
    # Common patterns
    text = re.sub(r'The post .* appeared first on .*', '', text)
    text = re.sub(r'Прочитајте повеќе на .*', '', text)
    text = re.sub(r'This article was originally published on .*', '', text)
    text = re.sub(r'Source: https?://.*', '', text)
    return text.strip()

def fetch_feed(source, url):
    """Fetch a single RSS feed and return entries."""
    try:
        feed = feedparser.parse(url)
        entries = feed.entries[:FEED_LIMIT]
        return source, entries, None
    except Exception as e:
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
            future_to_feed = {executor.submit(fetch_feed, s, u): s for s, u in RSS_FEEDS}
            for future in as_completed(future_to_feed):
                source, entries, err = future.result()
                if err:
                    errors.append((source, err))
                else:
                    for e in entries:
                        title = e.get("title", "")
                        link  = e.get("link", "")
                        desc  = e.get("summary", "") or e.get("description", "")
                        # Find lead image
                        image_url = None
                        if "media_content" in e and e.media_content:
                            image_url = e.media_content[0].get("url")
                        elif "links" in e:
                            for l in e.links:
                                if "image" in l.get("type", ""):
                                    image_url = l.get("href")
                                    break
                        if not image_url and "enclosures" in e and e.enclosures:
                            image_url = e.enclosures[0].get("url")
                        
                        if title and link:
                            all_entries.append((source, title, link, desc, image_url))

        new_count = 0
        for source, title, link, desc, image_url in all_entries:
            try:
                forced     = HARDCODED_FEED_CATEGORIES.get(source)
                category   = detect_category(title, description=desc, source=source, forced_category=forced)
                subcategory = detect_subcategory(title, description=desc) or ""
                cluster_id = clustering.find_or_create_cluster(title, recent_articles)
                now        = datetime.datetime.now()
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO articles (title, link, source, category, subcategory, cluster_id, created_at, image_url, description) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (link) DO NOTHING RETURNING id""",
                    (title, link, source, category, subcategory, cluster_id, now, image_url, clean_desc)
                )
                inserted = cur.fetchone()
                cur.close()
                
                if inserted:
                    recent_articles.insert(0, {"title": title, "cluster_id": cluster_id, "created_at": now})
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
    errors = []
    max_workers = min(len(DIASPORA_FEEDS), 20)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_feed = {executor.submit(fetch_feed, s, u): s for s, u, c in DIASPORA_FEEDS}
        for future in as_completed(future_to_feed):
            source, entries, err = future.result()
            if err:
                errors.append((source, err))
            else:
                cat, country = feed_meta[source]
                for e in entries:
                    title = e.get("title", "")
                    link  = e.get("link", "")
                    desc  = e.get("summary", "") or e.get("description", "")
                    # Find lead image
                    image_url = None
                    if "media_content" in e and e.media_content:
                        image_url = e.media_content[0].get("url")
                    if not image_url and "enclosures" in e and e.enclosures:
                        image_url = e.enclosures[0].get("url")
                    
                    if title and link:
                        all_entries.append((source, title, link, desc, image_url, cat, country))

    conn = get_db()
    try:
        new_count = 0
        for i, (source, title, link, desc, image_url, category, country) in enumerate(all_entries):
            try:
                display_title = normalize_headline(title)
                
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                cluster_id = clustering.find_or_create_cluster(display_title, diaspora_recent)
                now = datetime.datetime.now()

                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO articles 
                    (title, original_title, link, source, category, subcategory, cluster_id, 
                    created_at, image_url, description, original_description, country, is_translated) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
                    ON CONFLICT (link) DO NOTHING RETURNING id""",
                    (display_title, title, link, source, category, "", cluster_id,
                     now, image_url, clean_desc, clean_desc, country, 0)
                )
                row = cur.fetchone()
                cur.close()

                if row:
                    article_id = row[0]
                    # Dispatch background translation task
                    from tasks import translate_article_task
                    translate_article_task.delay(article_id, display_title, clean_desc)

                    diaspora_recent.insert(0, {"title": display_title, "cluster_id": cluster_id, "created_at": now})
                    if len(diaspora_recent) > CLUSTER_LOOKBACK:
                        diaspora_recent.pop()
                    new_count += 1
            except Exception as e:
                log.error(f"[diaspora] DB write error — {source} | {title[:40]}: {e}")

        conn.commit()
        return new_count, errors
    finally:
        conn.close()
