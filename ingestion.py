import re
import datetime
import feedparser
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import clustering
from ai_engine import translate_to_macedonian
from categories import detect_category, detect_subcategory, detect_country, normalize_headline, detect_topic
from database import db_manager as db, get_db
from config import FEED_LIMIT, CLUSTER_LOOKBACK, HARDCODED_FEED_CATEGORIES, JUNK_KEYWORDS
from embeddings import generate_embeddings_batch

log = logging.getLogger("presek")

def is_junk(title: str, desc: str) -> bool:
    """True if text contains blacklisted low-quality keywords."""
    text = f"{title} {desc}".lower()
    return any(word in text for word in JUNK_KEYWORDS)

def clean_rss_footer(text: str) -> str:
    """Removes common RSS footers like 'The post ... appeared first on ...'"""
    if not text: return ""
    text = re.sub(r'The post .* appeared first on .*', '', text)
    text = re.sub(r'Прочитајте повеќе на .*', '', text)
    text = re.sub(r'This article was originally published on .*', '', text)
    text = re.sub(r'Source: https?://.*', '', text)
    return text.strip()

def fetch_feed(source_name, url, limit=10):
    """Fetch a single RSS feed and return entries. Enforces a 12s timeout."""
    try:
        import requests as _req
        headers = {'User-Agent': 'Presek/1.0 RSS Reader (+https://presek.mk)'}
        resp = _req.get(url, timeout=12, headers=headers)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = feed.entries[:limit]
        log.debug(f"Fetched {len(entries)} articles from {source_name}")
        return source_name, entries, None
    except Exception as e:
        log.error(f"Failed to fetch feed from {source_name} ({url}): {e}")
        return source_name, [], str(e)

def extract_image_url(entry):
    """Extracts the best representative image URL from an RSS entry."""
    image_url = None
    if "media_content" in entry and entry.media_content:
        image_url = entry.media_content[0].get("url")
    elif "links" in entry:
        for l in entry.links:
            if "image" in l.get("type", ""):
                image_url = l.get("href")
                break
    if not image_url and "enclosures" in entry and entry.enclosures:
        image_url = entry.enclosures[0].get("url")
    return image_url

def get_active_sources():
    """Fetches all active sources from the database."""
    rows = db.execute("SELECT name, url, country, category, credibility, source_limit FROM sources WHERE is_active = TRUE")
    return [dict(r) for r in rows]

def cosine_dist(a, b):
    """Calculates cosine distance between two vectors (lists of floats)."""
    dot = sum(x*y for x, y in zip(a, b))
    norm_a = sum(x*x for x in a)**0.5
    norm_b = sum(x*x for x in b)**0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0

def ingest_all_sources():
    """
    Unified ingestion pipeline for all sources (local and international).
    Fetches, filters, embeds, clusters, and writes to DB.
    """
    conn = get_db()
    try:
        sources = get_active_sources()
        if not sources:
            log.warning("No active sources found in database.")
            return 0, []

        # 1. Gather recently seen data to avoid duplicates
        known_links = set()
        recent_by_source = defaultdict(list)
        
        # Look back 12h for duplicate detection
        lookback_time = datetime.datetime.now() - datetime.timedelta(hours=12)
        rows = conn.execute(
            "SELECT link, source, title FROM articles WHERE created_at >= %s",
            (lookback_time,)
        ).fetchall()
        for r in rows:
            known_links.add(r["link"])
            recent_by_source[r["source"]].append(r["title"].lower())

        # 2. Parallel Fetching
        candidates = []
        errors = []
        max_workers = min(len(sources), 30)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_source = {
                executor.submit(fetch_feed, s['name'], s['url'], s['source_limit']): s 
                for s in sources
            }
            for future in as_completed(future_to_source):
                source_name, entries, err = future.result()
                source_meta = next(s for s in sources if s['name'] == source_name)
                
                if err:
                    errors.append((source_name, err))
                else:
                    for e in entries:
                        title = e.get("title", "").strip()
                        link  = e.get("link", "")
                        
                        if not title or not link or link in known_links:
                            continue
                        
                        desc  = e.get("summary", "") or e.get("description", "")
                        if is_junk(title, desc):
                            continue
                            
                        # Same-Source duplicate detection
                        t_lower = title.lower()
                        if any(t_lower == rt or (len(t_lower) > 30 and rt.startswith(t_lower[:30])) 
                               for rt in recent_by_source[source_name]):
                            continue

                        image_url = extract_image_url(e)
                        
                        candidates.append({
                            "source": source_name,
                            "title": title,
                            "link": link,
                            "desc": desc,
                            "image_url": image_url,
                            "country": source_meta['country'],
                            "category": source_meta['category']
                        })

        if not candidates:
            return 0, errors

        # 3. Batch Embedding
        log.info(f"[ingestion] Generating embeddings for {len(candidates)} new articles...")
        texts_to_embed = [f"{c['title']} {c['desc'][:200]}" for c in candidates]
        embeddings = generate_embeddings_batch(texts_to_embed)

        # 4. Clustering & Preparation
        recent_rows = conn.execute(
            "SELECT title, cluster_id, created_at, category FROM articles ORDER BY created_at DESC LIMIT %s",
            (CLUSTER_LOOKBACK,)
        ).fetchall()
        recent_articles = [
            {"title": r["title"], "cluster_id": r["cluster_id"], "created_at": r["created_at"], "category": r["category"]} 
            for r in recent_rows
        ]

        from clustering import VECTOR_THRESHOLD
        
        prepared_rows = []
        batch_clusters = [] 
        international_inserted_ids = []

        for i, c in enumerate(candidates):
            try:
                emb = embeddings[i]
                title = c['title']
                desc = c['desc']
                source = c['source']
                
                # Metadata detection
                forced = HARDCODED_FEED_CATEGORIES.get(source)
                category = detect_category(title, description=desc, source=source, forced_category=forced)
                if not category:
                    category = c['category'] # Fallback to source category
                
                subcategory = detect_subcategory(title, description=desc) or ""
                topic = detect_topic(title, description=desc)
                
                # Normalization for international sources
                is_international = c['country'] != '🇲🇰'
                display_title = normalize_headline(title) if is_international else title
                original_title = title if is_international else ""

                # Clustering logic
                cluster_id = None
                if emb:
                    for bc in batch_clusters:
                        if bc['category'] == category and cosine_dist(emb, bc['embedding']) < VECTOR_THRESHOLD:
                            cluster_id = bc['cid']
                            break
                
                if not cluster_id:
                    cluster_id = clustering.find_or_create_cluster(display_title, recent_articles, embedding=emb, category=category)
                
                now = datetime.datetime.now()
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                # Prepare row for DB
                # Schema: (title, original_title, link, source, category, subcategory, cluster_id, created_at, image_url, description, original_description, country, is_translated, embedding, topic)
                prepared_rows.append((
                    display_title, 
                    original_title,
                    c['link'], 
                    source, 
                    category, 
                    subcategory, 
                    cluster_id, 
                    now, 
                    c['image_url'], 
                    clean_desc,
                    clean_desc if is_international else "",
                    c['country'],
                    0, # is_translated
                    str(emb) if emb else None, 
                    topic
                ))
                
                # Update local state for next items in same batch
                if emb:
                    batch_clusters.append({'cid': cluster_id, 'embedding': emb, 'category': category})
                recent_articles.insert(0, {"title": display_title, "cluster_id": cluster_id, "created_at": now, "category": category})
                if len(recent_articles) > CLUSTER_LOOKBACK:
                    recent_articles.pop()
                    
            except Exception as e:
                log.error(f"Processing error — {c['source']} | {c['title'][:40]}: {e}")

        # 5. Batch Write
        new_count = 0
        if prepared_rows:
            cur = conn.cursor()
            try:
                # Use psycopg2.extras.execute_values for performance
                from psycopg2.extras import execute_values
                
                sql = """
                    INSERT INTO articles (
                        title, original_title, link, source, category, subcategory, 
                        cluster_id, created_at, image_url, description, original_description, 
                        country, is_translated, embedding, topic
                    )
                    VALUES %s
                    ON CONFLICT (link) DO NOTHING
                    RETURNING id, country
                """
                execute_values(cur, sql, prepared_rows)
                results = cur.fetchall()
                new_count = len(results)
                
                # Collect IDs for translation
                for r_id, r_country in results:
                    if r_country != '🇲🇰':
                        international_inserted_ids.append(r_id)
                        
            except Exception as e:
                log.error(f"Batch insert error: {e}")
            finally:
                cur.close()

        conn.commit()
        
        # 6. Post-processing (Events & Translations)
        if new_count > 0:
            from utils import publish_event
            publish_event("updates", {"type": "new_articles", "count": new_count, "time": datetime.datetime.now()})
            
        if international_inserted_ids:
            from tasks import translate_article_task
            for article_id in international_inserted_ids:
                art = db.execute_one("SELECT title, description FROM articles WHERE id = %s", (article_id,))
                if art:
                    translate_article_task.delay(article_id, art["title"], art["description"])

        return new_count, errors
    finally:
        conn.close()

# Legacy wrappers to maintain compatibility with existing tasks.py calls
def ingest_feeds():
    """Wrapper for backward compatibility."""
    return ingest_all_sources()

def ingest_diaspora_feeds():
    """Wrapper for backward compatibility. Now does nothing as ingest_all_sources handles it."""
    return 0, []
