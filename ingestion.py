import re
import datetime
import asyncio
import feedparser
import logging
from collections import defaultdict
from typing import List, Dict, Any, Tuple, TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if TYPE_CHECKING:
    import httpx

import clustering
from ai_engine import translate_to_macedonian
from categories import detect_category, detect_subcategory, detect_country, normalize_headline, detect_topic
from database import db_manager as db, get_db
from config import FEED_LIMIT, CLUSTER_LOOKBACK, HARDCODED_FEED_CATEGORIES, JUNK_KEYWORDS
from embeddings import generate_embeddings_batch
from health import record_source_fetch, get_source_statuses

log = logging.getLogger("presek")

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "mkt_tok", "ref", "ref_src",
}

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
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), normalized_path, urlencode(query_items), ""))
    except Exception:
        return link.strip()


def normalize_candidate_title(title: str) -> str:
    """Create a stable title fingerprint for same-source duplicate checks."""
    if not title:
        return ""
    text = normalize_headline(re.sub(r"<[^>]+>", " ", title))
    text = re.sub(r"^\[(live|update|breaking|video|photo)\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(live|update|updated|breaking)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[\-–—|]\s*(live updates?|updated|video|photo|gallery)\s*$", "", text, flags=re.IGNORECASE)
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
        except Exception:
            pass
    return fallback_now

def extract_image_url(entry):
    """Extracts the best representative image URL from an RSS entry."""
    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _image_url_score(url: str, mime_type: str, width: int, height: int, source_rank: float) -> float:
        if not url or not re.match(r"^https?://", str(url).strip(), flags=re.IGNORECASE):
            return -100.0

        parsed = urlsplit(str(url).strip())
        path = (parsed.path or "").lower()
        query = (parsed.query or "").lower()
        combined = f"{path}?{query}"
        mime = str(mime_type or "").lower()

        score = source_rank
        if "image/" in mime or path.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
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

        if any(pattern in combined for pattern in ("thumb", "thumbnail", "sprite", "logo", "icon", "avatar", "favicon", "pixel", "small")):
            score -= 6.0
        if any(pattern in combined for pattern in ("hero", "lead", "main", "large", "full", "original")):
            score += 1.5

        return score

    candidates = []

    for item in getattr(entry, "media_content", None) or entry.get("media_content", []) or []:
        candidates.append({
            "url": item.get("url") or item.get("href"),
            "mime": item.get("type") or item.get("medium"),
            "width": _to_int(item.get("width")),
            "height": _to_int(item.get("height")),
            "source_rank": 3.0,
        })

    for item in getattr(entry, "links", None) or entry.get("links", []) or []:
        link_type = str(item.get("type") or "").lower()
        rel = str(item.get("rel") or "").lower()
        if "image" in link_type or rel == "enclosure":
            candidates.append({
                "url": item.get("href") or item.get("url"),
                "mime": item.get("type"),
                "width": _to_int(item.get("width")),
                "height": _to_int(item.get("height")),
                "source_rank": 2.0 if "image" in link_type else 1.4,
            })

    for item in getattr(entry, "enclosures", None) or entry.get("enclosures", []) or []:
        candidates.append({
            "url": item.get("url") or item.get("href"),
            "mime": item.get("type"),
            "width": _to_int(item.get("width")),
            "height": _to_int(item.get("height")),
            "source_rank": 1.0,
        })

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

async def fetch_feed_async(client: "httpx.AsyncClient", source: Dict[str, Any]) -> Tuple[str, List[Any], str | None]:
    """Asynchronously fetch and parse a single RSS feed."""
    name = source['name']
    url = source['url']
    limit = source.get('source_limit', 10)
    
    try:
        resp = await client.get(url, timeout=15.0, follow_redirects=True)
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
    dot = sum(x*y for x, y in zip(a, b))
    norm_a = sum(x*x for x in a)**0.5
    norm_b = sum(x*x for x in b)**0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0

async def ingest_all_sources_async():
    """
    Modern Async Ingestion Pipeline.
    Uses httpx for concurrent fetching and asyncio for non-blocking orchestration.
    """
    sources = get_active_sources()
    if not sources:
        log.warning("No active sources found.")
        return 0, []

    # 1. Duplicate detection setup
    known_links = set()
    recent_by_source = defaultdict(set)
    lookback_time = datetime.datetime.now() - datetime.timedelta(hours=12)
    
    with get_db() as conn:
        rows = conn.execute(
            "SELECT link, source, title FROM articles WHERE created_at >= %s",
            (lookback_time,)
        ).fetchall()
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
    
    headers = {'User-Agent': 'Presek/6.0 Async Reader (+https://presek.mk)'}
    import httpx

    async with httpx.AsyncClient(headers=headers, verify=True) as client:
        tasks = [fetch_feed_async(client, s) for s in sources]
        results = await asyncio.gather(*tasks)
        
        for source_name, entries, err in results:
            source_stats[source_name]["fetched"] = len(entries)
            if err:
                source_stats[source_name]["status"] = "error"
                source_stats[source_name]["error"] = str(err)
                errors.append((source_name, err))
                continue
            
            source_meta = next(s for s in sources if s['name'] == source_name)
            for e in entries:
                title = e.get("title", "").strip()
                link = normalize_feed_link(e.get("link", ""))
                title_key = normalize_candidate_title(title)

                if not title or not link or link in known_links or link in seen_links:
                    continue
                
                desc = e.get("summary", "") or e.get("description", "")
                if is_junk(title, desc):
                    continue

                if not title_key:
                    continue

                if title_key in recent_by_source[source_name] or title_key in seen_titles_by_source[source_name]:
                    continue

                published_at = parse_entry_timestamp(e, fallback_now=cycle_now)

                candidates.append({
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "desc": desc,
                    "image_url": extract_image_url(e),
                    "country": source_meta['country'],
                    "category": source_meta['category'],
                    "created_at": published_at,
                })
                seen_links.add(link)
                seen_titles_by_source[source_name].add(title_key)
                source_stats[source_name]["accepted"] += 1

            if source_stats[source_name]["accepted"] == 0 and source_stats[source_name]["fetched"] > 0:
                source_stats[source_name]["status"] = "warning"

    if not candidates:
        for source_name, stats in source_stats.items():
            record_source_fetch(
                source_name,
                stats["status"],
                fetched=stats["fetched"],
                accepted=stats["accepted"],
                error=stats["error"],
            )
        return 0, errors

    # 3. Batch Processing (CPU/API intensive parts)
    log.info(f"[ingestion] Processing {len(candidates)} candidates...")
    
    # Generate embeddings in one batch
    texts_to_embed = [f"{c['title']} {c['desc'][:200]}" for c in candidates]
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(None, generate_embeddings_batch, texts_to_embed)

    # 4. Clustering & DB Preparation
    # (Rest of the logic remains mostly same but wrapped in async orchestration)
    new_count = 0
    with get_db() as conn:
        recent_rows = conn.execute(
            "SELECT title, cluster_id, created_at, category FROM articles ORDER BY created_at DESC LIMIT %s",
            (CLUSTER_LOOKBACK,)
        ).fetchall()
        recent_articles = [dict(r) for r in recent_rows]

        from clustering import VECTOR_THRESHOLD
        prepared_rows = []
        batch_clusters = []
        international_ids = []

        for i, c in enumerate(candidates):
            try:
                emb = embeddings[i]
                forced = HARDCODED_FEED_CATEGORIES.get(c['source'])
                category = detect_category(c['title'], description=c['desc'], source=c['source'], forced_category=forced) or c['category']
                subcategory = detect_subcategory(c['title'], description=c['desc']) or ""
                topic = detect_topic(c['title'], description=c['desc'])
                
                is_intl = c['country'] != '🇲🇰'
                display_title = normalize_headline(c['title']) if is_intl else c['title']
                
                cluster_id = None
                if emb:
                    for bc in batch_clusters:
                        if bc['category'] == category and cosine_dist(emb, bc['embedding']) < VECTOR_THRESHOLD:
                            cluster_id = bc['cid']
                            break
                
                if not cluster_id:
                    # find_or_create_cluster is currently synchronous
                    cluster_id = clustering.find_or_create_cluster(display_title, recent_articles, embedding=emb, category=category)
                
                clean_desc = re.sub(r'<[^>]+>', '', c['desc']).strip() if c['desc'] else ""
                clean_desc = clean_rss_footer(clean_desc)[:500]
                created_at = c.get("created_at") or cycle_now

                prepared_rows.append((
                    display_title, c['title'] if is_intl else "",
                    c['link'], c['source'], category, subcategory, 
                    cluster_id, created_at, c['image_url'], clean_desc,
                    clean_desc if is_intl else "", c['country'], 0,
                    str(emb) if emb else None, topic
                ))

                if emb:
                    batch_clusters.append({'cid': cluster_id, 'embedding': emb, 'category': category})
                recent_articles.insert(0, {"title": display_title, "cluster_id": cluster_id, "created_at": created_at, "category": category})
                if len(recent_articles) > CLUSTER_LOOKBACK: recent_articles.pop()

            except Exception as e:
                log.error(f"[ingest] error processing {c['source']}: {e}")

        # Batch Insert
        if prepared_rows:
            from psycopg2.extras import execute_values
            cur = conn.cursor()
            sql = """
                INSERT INTO articles (
                    title, original_title, link, source, category, subcategory, 
                    cluster_id, created_at, image_url, description, original_description, 
                    country, is_translated, embedding, topic
                ) VALUES %s ON CONFLICT (link) DO NOTHING RETURNING id, country
            """
            execute_values(cur, sql, prepared_rows)
            results = cur.fetchall()
            new_count = len(results)
            conn.commit()

            successful_sources = [name for name, stats in source_stats.items() if stats["fetched"] > 0 and not stats["error"]]
            if successful_sources:
                conn.execute(
                    "UPDATE sources SET last_fetched = NOW() WHERE name = ANY(%s)",
                    (successful_sources,),
                )
                conn.commit()
            
            # Post-ingestion tasks
            if new_count > 0:
                from utils import publish_event
                publish_event("updates", {"type": "new_articles", "count": new_count, "time": cycle_now})
                
                # Translation triggers (async via Celery as before)
                from tasks import translate_article_task
                for r_id, r_country in results:
                    if r_country != '🇲🇰':
                        art = db.execute_one("SELECT title, description FROM articles WHERE id = %s", (r_id,))
                        if art:
                            translate_article_task.delay(r_id, art["title"], art["description"])

    current_statuses = get_source_statuses()
    for source_name, stats in source_stats.items():
        record_source_fetch(
            source_name,
            stats["status"],
            fetched=stats["fetched"],
            accepted=stats["accepted"],
            error=stats["error"],
        )
        updated_status = get_source_statuses().get(source_name) or current_statuses.get(source_name) or {}
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

    return new_count, errors

def ingest_all_sources():
    """Synchronous wrapper for Celery/Script compatibility."""
    return asyncio.run(ingest_all_sources_async())

def ingest_feeds():
    return ingest_all_sources()

def ingest_diaspora_feeds():
    return 0, []
