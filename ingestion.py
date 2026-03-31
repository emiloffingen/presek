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
from embeddings import generate_embeddings_batch

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

def _get_last_seen_links(conn, source, limit=50):
    """Get recently seen links for a source to skip duplicates early."""
    rows = conn.execute(
        "SELECT link FROM articles WHERE source = %s ORDER BY created_at DESC LIMIT %s",
        (source, limit)
    ).fetchall()
    return {r["link"] for r in rows}

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
        # Pre-fetch known links to skip duplicates early
        known_links = set()
        link_rows = conn.execute(
            "SELECT link FROM articles WHERE created_at >= %s",
            (datetime.datetime.now() - datetime.timedelta(days=2),)
        ).fetchall()
        known_links = {r["link"] for r in link_rows}

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
                        if not title or not link or link in known_links:
                            continue
                        desc  = e.get("summary", "") or e.get("description", "")
                        
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

                        all_entries.append((source, title, link, desc, image_url))

        if not all_entries:
            return 0, errors

        # ── Presek 2.0: Batch Generate Embeddings ──
        log.info(f"[ingestion] Generating embeddings for {len(all_entries)} new articles...")
        texts_to_embed = [f"{t} {d[:200]}" for s, t, l, d, i in all_entries]
        embeddings = generate_embeddings_batch(texts_to_embed)

        # Pre-fetch recent articles for TF-IDF fallback
        recent_rows = conn.execute(
            "SELECT title, cluster_id, created_at FROM articles ORDER BY created_at DESC LIMIT %s",
            (CLUSTER_LOOKBACK,)
        ).fetchall()
        recent_articles = [{"title": r["title"], "cluster_id": r["cluster_id"], "created_at": r["created_at"]} for r in recent_rows]

        prepared_rows = []
        # Keep track of clusters created in this batch for local matching
        batch_clusters: list[dict] = [] # List of {cid, embedding}

        for i, (source, title, link, desc, image_url) in enumerate(all_entries):
            try:
                emb = embeddings[i]
                forced     = HARDCODED_FEED_CATEGORIES.get(source)
                category   = detect_category(title, description=desc, source=source, forced_category=forced)
                subcategory = detect_subcategory(title, description=desc) or ""
                
                # Try to find cluster in batch first (to group identical stories in same fetch)
                cluster_id = None
                if emb:
                    from clustering import VECTOR_THRESHOLD
                    def cosine_dist(a, b):
                        dot = sum(x*y for x, y in zip(a, b))
                        norm_a = sum(x*x for x in a)**0.5
                        norm_b = sum(x*x for x in b)**0.5
                        return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0

                    for bc in batch_clusters:
                        if cosine_dist(emb, bc['embedding']) < VECTOR_THRESHOLD:
                            cluster_id = bc['cid']
                            break
                
                if not cluster_id:
                    cluster_id = clustering.find_or_create_cluster(title, recent_articles, embedding=emb)
                
                now = datetime.datetime.now()
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]

                # Store result for DB
                emb_str = str(emb) if emb else None
                prepared_rows.append((title, link, source, category, subcategory, cluster_id, now, image_url, clean_desc, emb_str))
                
                # Update trackers
                if emb:
                    batch_clusters.append({'cid': cluster_id, 'embedding': emb})
                recent_articles.insert(0, {"title": title, "cluster_id": cluster_id, "created_at": now})
                if len(recent_articles) > CLUSTER_LOOKBACK:
                    recent_articles.pop()
                    
            except Exception as e:
                log.error(f"Processing error — {source} | {title[:40]}: {e}")

        # Batch insert
        new_count = 0
        if prepared_rows:
            from psycopg2.extras import execute_values
            cur = conn.cursor()
            try:
                result = execute_values(
                    cur,
                    """INSERT INTO articles (title, link, source, category, subcategory, cluster_id, created_at, image_url, description, embedding)
                       VALUES %s
                       ON CONFLICT (link) DO NOTHING RETURNING id""",
                    prepared_rows,
                    fetch=True
                )
                new_count = len(result)
            except Exception as e:
                log.error(f"Batch insert error: {e}")
            finally:
                cur.close()

        conn.commit()
        if new_count > 0:
            from utils import publish_event
            publish_event("updates", {"type": "new_articles", "count": new_count, "time": datetime.datetime.now()})
        return new_count, errors
    finally:
        conn.close()


def ingest_diaspora_feeds():
    """Fetch diaspora RSS feeds and write to DB separately (without translation)."""
    conn = get_db()
    # Pre-fetch known links to skip duplicates early
    known_links_rows = conn.execute(
        "SELECT link FROM articles WHERE country != '🇲🇰' AND created_at >= %s",
        (datetime.datetime.now() - datetime.timedelta(days=2),)
    ).fetchall()
    known_links = {r["link"] for r in known_links_rows}
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
                    if not title or not link or link in known_links:
                        continue
                    desc  = e.get("summary", "") or e.get("description", "")
                    
                    image_url = None
                    if "media_content" in e and e.media_content:
                        image_url = e.media_content[0].get("url")
                    if not image_url and "enclosures" in e and e.enclosures:
                        image_url = e.enclosures[0].get("url")

                    all_entries.append((source, title, link, desc, image_url, cat, country))

    if not all_entries:
        return 0, errors

    # ── Presek 2.0: Batch Generate Embeddings ──
    log.info(f"[diaspora] Generating embeddings for {len(all_entries)} articles...")
    texts_to_embed = [f"{t} {d[:200]}" for s, t, l, d, i, c, cy in all_entries]
    embeddings = generate_embeddings_batch(texts_to_embed)

    conn = get_db()
    try:
        # Pre-fetch recent articles for TF-IDF fallback
        diaspora_recent = conn.execute(
            "SELECT title, cluster_id, created_at FROM articles WHERE country != '🇲🇰' ORDER BY created_at DESC LIMIT %s",
            (CLUSTER_LOOKBACK,)
        ).fetchall()
        diaspora_recent = [{"title": r["title"], "cluster_id": r["cluster_id"], "created_at": r["created_at"]} for r in diaspora_recent]

        prepared_rows = []
        batch_clusters: list[dict] = []

        for i, (source, title, link, desc, image_url, category, country) in enumerate(all_entries):
            try:
                emb = embeddings[i]
                display_title = normalize_headline(title)
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip() if desc else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                
                # Batch match
                cluster_id = None
                if emb:
                    from clustering import VECTOR_THRESHOLD
                    def cosine_dist(a, b):
                        dot = sum(x*y for x, y in zip(a, b))
                        norm_a = sum(x*x for x in a)**0.5
                        norm_b = sum(x*x for x in b)**0.5
                        return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0

                    for bc in batch_clusters:
                        if cosine_dist(emb, bc['embedding']) < VECTOR_THRESHOLD:
                            cluster_id = bc['cid']
                            break
                
                if not cluster_id:
                    cluster_id = clustering.find_or_create_cluster(display_title, diaspora_recent, embedding=emb)
                
                now = datetime.datetime.now()
                emb_str = str(emb) if emb else None

                prepared_rows.append((display_title, title, link, source, category, "", cluster_id,
                                     now, image_url, clean_desc, clean_desc, country, 0, emb_str))
                
                if emb:
                    batch_clusters.append({'cid': cluster_id, 'embedding': emb})
                diaspora_recent.insert(0, {"title": display_title, "cluster_id": cluster_id, "created_at": now})
                if len(diaspora_recent) > CLUSTER_LOOKBACK:
                    diaspora_recent.pop()
            except Exception as e:
                log.error(f"[diaspora] Processing error — {source} | {title[:40]}: {e}")

        # Batch insert
        new_count = 0
        inserted_ids = []
        if prepared_rows:
            from psycopg2.extras import execute_values
            cur = conn.cursor()
            try:
                inserted_ids = execute_values(
                    cur,
                    """INSERT INTO articles
                    (title, original_title, link, source, category, subcategory, cluster_id,
                    created_at, image_url, description, original_description, country, is_translated, embedding)
                    VALUES %s
                    ON CONFLICT (link) DO NOTHING RETURNING id""",
                    prepared_rows,
                    fetch=True
                )
                new_count = len(inserted_ids)
            except Exception as e:
                log.error(f"[diaspora] Batch insert error: {e}")
            finally:
                cur.close()

        conn.commit()

        # Dispatch translation tasks
        if inserted_ids:
            from tasks import translate_article_task
            for row in inserted_ids:
                article_id = row[0]
                art = conn.execute("SELECT title, description FROM articles WHERE id = %s", (article_id,)).fetchone()
                if art:
                    translate_article_task.delay(article_id, art["title"], art["description"])

        return new_count, errors
    finally:
        conn.close()

