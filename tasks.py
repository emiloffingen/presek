import logging
import datetime
import re as _re
import time
from collections import Counter
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import prune_db
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, OPENCLAW_URL, OPENCLAW_TOKEN
from ai_engine import translate_to_macedonian, auto_summarize_top_clusters, _call_ai, clean_json_response, generate_cover_art
from database import get_db
from prompts import CATEGORIZATION_SYSTEM_PROMPT, TAGGING_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, TOPIC_SYSTEM_PROMPT, DAILY_BRIEF_SYSTEM_PROMPT, ENTITY_EXTRACTION_PROMPT
from categories import ALLOWED_CATEGORIES
from health import record_refresh

log = logging.getLogger("presek_celery")

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def summarize_article_task(article_id, title):
    """Asynchronously generates a summary for a single article."""
    conn = None
    try:
        summary, tier = _call_ai(title, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
        if summary:
            summary_res = clean_json_response(summary)
            # clean_json_response might return dict for synthesis but here it should be string
            final_summary = summary_res.get('summary', str(summary_res)) if isinstance(summary_res, dict) else summary_res
            conn = get_db()
            conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (final_summary, article_id))
            conn.commit()
    except Exception as e:
        log.warning(f"[auto-summarize] DB write failed for article {article_id}: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def synthesize_cluster_task(cluster_id, content):
    """Asynchronously generates a synthesis for a cluster with multiple perspectives."""
    conn = None
    try:
        raw_res, tier = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True, task_type="synthesis")
        if raw_res:
            res = clean_json_response(raw_res)
            summary = ""
            perspectives = []

            if isinstance(res, dict):
                summary = res.get('summary', '')
                perspectives = res.get('perspectives', [])
            else:
                summary = res

            now = datetime.datetime.now()
            import json as _json
            conn = get_db()
            conn.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary, perspectives = EXCLUDED.perspectives, created_at = EXCLUDED.created_at""",
                (cluster_id, summary, _json.dumps(perspectives), now)
            )
            conn.commit()

            # Generate cover art only if NO article in the cluster has an image
            any_image = conn.execute("SELECT 1 FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL AND image_url != '' LIMIT 1", (cluster_id,)).fetchone()
            if not any_image:
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    conn.execute("UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 1)", (img_url, cluster_id))
                    conn.commit()
    except Exception as e:
        log.warning(f"[auto-summarize] Cluster synthesis failed for {cluster_id}: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=2)
def run_ingestion():
    """Periodic task to ingest regular and diaspora feeds."""
    log.info("Starting regular feed ingestion...")
    new_count, errors = ingest_feeds()
    
    log.info("Starting diaspora feed ingestion...")
    d_count, d_errors = ingest_diaspora_feeds()
    
    # Update health monitoring
    record_refresh(new_count + d_count, errors + d_errors)
    
    log.info("Starting recategorization for suspect clusters...")
    recategorize_clusters_task.delay()

    log.info("Starting metadata generation (tagging)...")
    generate_cluster_metadata_task.delay()

    log.info("Starting topical classification...")
    classify_topics_task.delay()

    log.info("Starting entity extraction...")
    extract_entities_task.delay()
    
    log.info("Starting auto-summarization...")
    from utils import rank_articles_in_cluster, score_cluster
    auto_summarize_top_clusters(rank_articles_in_cluster, score_cluster)
    
    log.info("Checking for breaking news to notify...")
    try:
        from notifier import BreakingNewsNotifier
        from config import NTFY_TOPIC, BREAKING_SCORE_THRESHOLD
        from collections import defaultdict
        
        notifier = BreakingNewsNotifier(topic=NTFY_TOPIC, threshold=3)
        conn = get_db()
        try:
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=1)
            rows = conn.execute("SELECT * FROM articles WHERE created_at >= %s", (cutoff,)).fetchall()
        finally:
            conn.close()
        
        if rows:
            clusters_map = defaultdict(list)
            for r in rows:
                clusters_map[r["cluster_id"]].append(dict(r))
            
            for cid, arts in clusters_map.items():
                sorted_arts = rank_articles_in_cluster(arts)
                score = score_cluster(sorted_arts)
                source_names = list({a["source"] for a in sorted_arts})

                if score >= BREAKING_SCORE_THRESHOLD or len(source_names) >= 3:
                    top = sorted_arts[0]
                    # Use synthesis/description for extra detail
                    desc = top.get("description") or ""
                    if len(desc) > 300:
                        desc = desc[:297] + "..."
                    # Pick best image: prefer cover art, then any article image
                    image = None
                    for a in sorted_arts:
                        if a.get("image_url"):
                            image = a["image_url"]
                            break
                    notifier.notify(
                        top["title"], len(source_names), cid,
                        description=desc, sources=source_names, image_url=image,
                    )
    except Exception as e:
        log.error(f"Notification check failed: {e}")
    
    log.info("Finished ingestion cycle.")

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def generate_daily_brief_task():
    """
    Generate a cohesive narrative summary of the top stories.
    Runs once a day (usually in the morning).
    """
    conn = None
    try:
        from utils import rank_articles_in_cluster, score_cluster
        from collections import defaultdict
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)

        # Get top clusters from the last 24h
        rows = conn.execute("SELECT * FROM articles WHERE created_at >= %s", (cutoff,)).fetchall()

        if not rows:
            return

        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(dict(r))

        ranked = []
        for cid, arts in clusters_map.items():
            sorted_arts = rank_articles_in_cluster(arts)
            s = score_cluster(sorted_arts)
            ranked.append((cid, sorted_arts, s))

        ranked.sort(key=lambda x: x[2], reverse=True)
        top_5 = ranked[:5]

        # Collect summaries/titles for context
        brief_context = []
        for cid, arts, s in top_5:
            # Check for synthesis first
            syn = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cid,)).fetchone()
            content = syn['summary'] if syn else arts[0]['title']
            brief_context.append(f"Тема {len(brief_context)+1}: {content}")

        context_text = "\n\n".join(brief_context)

        brief_text, tier = _call_ai(context_text, DAILY_BRIEF_SYSTEM_PROMPT, max_tokens=1000, task_type="daily_brief")

        if brief_text:
            today = datetime.date.today()
            conn.execute(
                "INSERT INTO daily_briefings (date, content) VALUES (%s, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content",
                (today, brief_text)
            )
            conn.commit()
            log.info(f"[daily-brief] Generated brief for {today} via {tier}")
    except Exception as e:
        log.error(f"Daily brief generation failed: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def generate_cluster_metadata_task():
    """
    Background task to generate tags for top clusters from the last 24h.
    """
    conn = None
    try:
        import json
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)

        # Get clusters from last 24h that don't have metadata yet
        rows = conn.execute("""
            SELECT cluster_id, title, description
            FROM articles
            WHERE created_at >= %s
              AND cluster_id NOT IN (SELECT cluster_id FROM cluster_metadata)
            GROUP BY cluster_id, title, description
            LIMIT 20
        """, (cutoff,)).fetchall()

        if not rows:
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"

            res, tier = _call_ai(text, TAGGING_SYSTEM_PROMPT, max_tokens=100, task_type="tagging")
            if res:
                try:
                    # Clean the response to ensure it's a valid JSON list
                    clean_res = res.strip().replace('```json', '').replace('```', '').strip()
                    tags = json.loads(clean_res)
                    if isinstance(tags, list):
                        conn.execute(
                            "INSERT INTO cluster_metadata (cluster_id, tags) VALUES (%s, %s) ON CONFLICT (cluster_id) DO UPDATE SET tags = EXCLUDED.tags",
                            (cid, tags)
                        )
                        conn.commit()
                except Exception as e:
                    log.warning(f"[tagging] Failed to parse tags for {cid}: {e}")
    except Exception as e:
        log.error(f"Metadata generation task failed: {e}")
    finally:
        if conn:
            conn.close()

# ── Entity normalization map (Latin → Cyrillic canonical, case-insensitive lookup) ──
ENTITY_ALIASES: dict[str, tuple[str, str]] = {
    # (canonical_name, entity_type)
    "donald trump":         ("Доналд Трамп", "PERSON"),
    "trump":                ("Доналд Трамп", "PERSON"),
    "трамп":                ("Доналд Трамп", "PERSON"),
    "putin":                ("Владимир Путин", "PERSON"),
    "путин":                ("Владимир Путин", "PERSON"),
    "vladimir putin":       ("Владимир Путин", "PERSON"),
    "biden":                ("Џо Бајден", "PERSON"),
    "бајден":               ("Џо Бајден", "PERSON"),
    "joe biden":            ("Џо Бајден", "PERSON"),
    "zelensky":             ("Володимир Зеленски", "PERSON"),
    "zelenskyy":            ("Володимир Зеленски", "PERSON"),
    "зеленски":             ("Володимир Зеленски", "PERSON"),
    "macron":               ("Емануел Макрон", "PERSON"),
    "макрон":               ("Емануел Макрон", "PERSON"),
    "erdogan":              ("Реџеп Ердоган", "PERSON"),
    "ердоган":              ("Реџеп Ердоган", "PERSON"),
    "vucic":                ("Александар Вучиќ", "PERSON"),
    "вучиќ":                ("Александар Вучиќ", "PERSON"),
    "vučić":                ("Александар Вучиќ", "PERSON"),
    "мицкоски":             ("Христијан Мицкоски", "PERSON"),
    "mickoski":             ("Христијан Мицкоски", "PERSON"),
    "ковачевски":           ("Димитар Ковачевски", "PERSON"),
    "kovachevski":          ("Димитар Ковачевски", "PERSON"),
    "пендаровски":          ("Стево Пендаровски", "PERSON"),
    "pendarovski":          ("Стево Пендаровски", "PERSON"),
    "сиљановска":           ("Гордана Сиљановска-Давкова", "PERSON"),
    "сиљановска-давкова":   ("Гордана Сиљановска-Давкова", "PERSON"),
    # Organizations
    "nato":                 ("НАТО", "ORG"),
    "нато":                 ("НАТО", "ORG"),
    "eu":                   ("ЕУ", "ORG"),
    "еу":                   ("ЕУ", "ORG"),
    "european union":       ("ЕУ", "ORG"),
    "un":                   ("ОН", "ORG"),
    "united nations":       ("ОН", "ORG"),
    "who":                  ("СЗО", "ORG"),
    "сзо":                  ("СЗО", "ORG"),
    "вмро-дпмне":           ("ВМРО-ДПМНЕ", "ORG"),
    "vmro-dpmne":           ("ВМРО-ДПМНЕ", "ORG"),
    "сдсм":                 ("СДСМ", "ORG"),
    "sdsm":                 ("СДСМ", "ORG"),
    "собрание":             ("Собрание", "ORG"),
    "влада":                ("Влада", "ORG"),
    "democrats":            ("Демократи", "ORG"),
    "republicans":          ("Републиканци", "ORG"),
}

def _normalize_entity(name: str, etype: str) -> tuple[str, str]:
    """Normalize entity name via alias map, return (canonical_name, type)."""
    key = name.lower().strip()
    if key in ENTITY_ALIASES:
        return ENTITY_ALIASES[key]
    return name.strip(), etype.strip()


# Pattern for Cyrillic proper noun sequences (2-3 capitalized words)
_CYRILLIC_NAME_RE = _re.compile(
    r'\b([А-ШЃЅЈЉЊЌЏа-шѓѕјљњќџ]*[А-ШЃЅЈЉЊЌЏ][а-шѓѕјљњќџ]{2,})'
    r'(?:\s+([А-ШЃЅЈЉЊЌЏа-шѓѕјљњќџ]*[А-ШЃЅЈЉЊЌЏ][а-шѓѕјљњќџ]{2,})){1,2}'
)

# Known MK org patterns
_ORG_KEYWORDS = {
    'влада', 'собрание', 'совет', 'министерство', 'суд', 'полиција',
    'комисија', 'агенција', 'фонд', 'партија', 'странка',
    'вмро-дпмне', 'сдсм', 'левица', 'алтернатива', 'дуи',
}

# Known locations / geographic names to filter out (not persons)
_LOCATION_NAMES = {
    'блискиот исток', 'кисела вода', 'ново лисиче', 'гази баба',
    'ѓорче петров', 'карпош', 'центар', 'аеродром', 'чаир', 'бутел',
    'шуто оризари', 'сарај', 'голема албанија', 'северна македонија',
    'саудиска арабија', 'нова зеландија', 'јужна кореја', 'северна кореја',
    'средна африка', 'западен балкан', 'источна европа', 'западна европа',
    'централна азија', 'јужна америка', 'северна америка',
    'стара чаршија', 'матка', 'водно', 'скопска црна гора',
    'охридско езеро', 'стар град', 'нови сад', 'бања лука',
    'црна гора', 'светиот гроб', 'света софија', 'свети николе',
    'нова година', 'стара година', 'велигденски празници',
    'европска унија', 'обединети нации',
}

# Title/role prefixes to strip from entity names
_TITLE_PREFIXES = _re.compile(
    r'^(Претседателот|Премиерот|Министерот|Градоначалникот|Обвинителот|Обвинителката|'
    r'Амбасадорот|Портпаролот|Директорот|Професорот|Генералот|Папата|'
    r'Претседателката|Министерката|Директорката|Портпаролката|'
    r'Обвинетиот|Обвинетата|Осуденикот|Осудената|Судијата|'
    r'Поранешниот|Поранешната|Актуелниот|Актуелната)\s+',
    _re.UNICODE
)

def _extract_entities_local(titles: list[str]) -> list[tuple[str, str]]:
    """
    Fast regex-based entity extraction from a list of titles.
    Returns [(name, type), ...] — no AI calls needed.
    """
    name_counts: Counter = Counter()

    for title in titles:
        if not title:
            continue
        # Find multi-word Cyrillic proper noun sequences
        for m in _CYRILLIC_NAME_RE.finditer(title):
            full = m.group(0).strip()
            # Strip title/role prefixes ("Премиерот Мицкоски" → "Мицкоски" won't match 2-word,
            # but "Претседателот Стево Пендаровски" → "Стево Пендаровски")
            cleaned = _TITLE_PREFIXES.sub('', full).strip()
            # After stripping, must still be a multi-word name
            if ' ' not in cleaned:
                continue
            name_counts[cleaned] += 1

    entities = []
    seen = set()
    for name, count in name_counts.most_common(20):
        if count < 1:
            continue
        lower = name.lower()
        # Skip known locations
        if lower in _LOCATION_NAMES:
            continue
        if lower in seen:
            continue
        # Determine type
        if any(kw in lower for kw in _ORG_KEYWORDS):
            etype = "ORG"
        else:
            etype = "PERSON"
        canonical, etype = _normalize_entity(name, etype)
        if canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        entities.append((canonical, etype))

    return entities


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def extract_entities_task():
    """
    Two-phase entity extraction:
    1. Fast local regex pass on ALL clusters (no AI cost)
    2. AI-powered extraction for top clusters (richer context with multiple titles)
    """
    conn = None
    try:
        import json
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)

        # ── Phase 1: Fast local extraction for all clusters without entities ──
        local_rows = conn.execute("""
            SELECT cluster_id, array_agg(title) as titles
            FROM articles
            WHERE created_at >= %s
              AND cluster_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM cluster_entities e WHERE e.cluster_id = articles.cluster_id)
            GROUP BY cluster_id
        """, (cutoff,)).fetchall()

        local_count = 0
        for r in local_rows:
            cid = r['cluster_id']
            titles = r['titles'] or []
            entities = _extract_entities_local(titles)
            for name, etype in entities:
                if name and len(name) >= 3:
                    conn.execute(
                        "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT (cluster_id, entity_name) DO NOTHING",
                        (cid, name, etype)
                    )
            if entities:
                local_count += 1
        conn.commit()
        log.info(f"[entities] Phase 1 (local): extracted entities for {local_count}/{len(local_rows)} clusters")

        # ── Phase 2: AI extraction for top clusters (2+ sources, no entities yet or only local) ──
        ai_rows = conn.execute("""
            SELECT cluster_id, array_agg(DISTINCT title) as titles,
                   array_agg(DISTINCT source) as sources,
                   MAX(description) as description
            FROM articles
            WHERE created_at >= %s AND cluster_id IS NOT NULL
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT source) >= 2
              AND NOT EXISTS (SELECT 1 FROM cluster_entities e WHERE e.cluster_id = articles.cluster_id)
            ORDER BY COUNT(*) DESC
            LIMIT 30
        """, (cutoff,)).fetchall()

        for r in ai_rows:
            cid = r['cluster_id']
            titles = r['titles'] or []
            # Build richer context with multiple titles
            titles_text = "\n".join(f"- {t}" for t in titles[:6])
            text = f"Наслови:\n{titles_text}\nОпис: {r['description'] or ''}"

            res, tier = _call_ai(text, ENTITY_EXTRACTION_PROMPT, max_tokens=500, json_mode=True, task_type="entity")
            if res:
                try:
                    data = clean_json_response(res)
                    entities = data.get('entities', []) if isinstance(data, dict) else []
                    for ent in entities:
                        name = ent.get('name', '').strip()
                        etype = ent.get('type', 'PERSON').strip()
                        if name:
                            name, etype = _normalize_entity(name, etype)
                            conn.execute(
                                "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT (cluster_id, entity_name) DO NOTHING",
                                (cid, name, etype)
                            )
                    conn.commit()
                except Exception as e:
                    log.warning(f"[entities] Failed to parse AI response for {cid}: {e}")
        log.info(f"[entities] Phase 2 (AI): processed {len(ai_rows)} multi-source clusters")
    except Exception as e:
        log.error(f"Entity extraction task failed: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def classify_topics_task():
    """
    Background task to classify untagged clusters into topical categories (Politics, Sport, etc.)
    """
    conn = None
    try:
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)

        # Find clusters created in last 24h where the topic is still 'Вести' (default)
        rows = conn.execute("""
            SELECT cluster_id, title, description
            FROM articles
            WHERE created_at >= %s AND topic = 'Вести'
            GROUP BY cluster_id, title, description
            LIMIT 30
        """, (cutoff,)).fetchall()

        if not rows:
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"

            res, tier = _call_ai(text, TOPIC_SYSTEM_PROMPT, max_tokens=10, task_type="topic")
            if res:
                topic = res.strip().strip('"').strip("'").strip('.')
                # Simple validation
                valid_topics = ['Политика', 'Економија', 'Технологија', 'Спорт', 'Забава', 'Здравје', 'Вести']
                if topic in valid_topics:
                    log.info(f"[topic] Cluster {cid} -> {topic}")
                    conn.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, cid))
                    conn.commit()
    except Exception as e:
        log.error(f"Topic classification task failed: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def recategorize_clusters_task():
    """
    Background task to find 'Македонија' clusters with multiple sources
    and ask AI if they should be in a different category.
    """
    conn = None
    try:
        conn = get_db()
        # Find clusters with 2+ sources currently in 'Македонија' created in last 12h
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=12)
        rows = conn.execute("""
            SELECT cluster_id, title, description
            FROM articles
            WHERE category = 'Македонија'
              AND created_at >= %s
            Group BY cluster_id, title, description
            HAVING COUNT(cluster_id) >= 2
            LIMIT 20
        """, (cutoff,)).fetchall()

        if not rows:
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"

            new_cat, tier = _call_ai(text, CATEGORIZATION_SYSTEM_PROMPT, max_tokens=10, task_type="categorize")
            if new_cat:
                new_cat = new_cat.strip().strip('"').strip("'")
                if new_cat in ALLOWED_CATEGORIES and new_cat != 'Македонија':
                    log.info(f"[recategorize] Cluster {cid}: Македонија -> {new_cat} (via {tier})")
                    conn.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (new_cat, cid))
                    conn.commit()
    except Exception as e:
        log.error(f"Recategorize task failed: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=2)
def send_daily_digest_task():
    """
    Periodic task to send a daily digest of the top stories to ntfy and email subscribers.
    """
    from digest import fetch_top_stories, send_ntfy_digest, render_html, send_email, mk_date
    from config import NTFY_TOPIC
    import os
    
    log.info("Generating and sending daily digest...")
    try:
        # Fetch top stories for the last 24 hours
        stories_by_cat = fetch_top_stories(days=1, per_category=3)
        if not stories_by_cat:
            log.warning("No stories found for the daily digest.")
            return

        # 1. Send via ntfy
        send_ntfy_digest(stories_by_cat, NTFY_TOPIC, period_days=1)
        
        # 2. Send via Email if SMTP is configured
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")
        smtp_host = os.environ.get("SMTP_HOST")
        smtp_port = os.environ.get("SMTP_PORT")
        
        if smtp_user and smtp_pass:
            now = datetime.datetime.now()
            start = now - datetime.timedelta(days=1)
            html = render_html(stories_by_cat, start, now)
            subject = f"Пресек — Дневен преглед {mk_date(start)} — {mk_date(now)}"

            conn = get_db()
            try:
                subs = conn.execute("SELECT email FROM subscribers").fetchall()
            finally:
                conn.close()

            for sub in subs:
                send_email(html, subject, smtp_user, smtp_pass, sub["email"], smtp_host, smtp_port)
                
    except Exception as e:
        log.error(f"Daily digest task failed: {e}")

@celery_app.task
def cleanup_cover_art_task():
    """Background task to remove orphaned cover art images."""
    from ai_engine import cleanup_cover_art
    cleanup_cover_art()

@celery_app.task
def backfill_cover_art_task():
    """Generate cover art for clusters that have synthesis but no images."""
    conn = None
    try:
        conn = get_db()
        # Find clusters with synthesis but where NO article has an image
        rows = conn.execute("""
            SELECT cs.cluster_id, cs.summary
            FROM cluster_summaries cs
            WHERE NOT EXISTS (
                SELECT 1 FROM articles a
                WHERE a.cluster_id = cs.cluster_id
                AND a.image_url IS NOT NULL AND a.image_url != ''
            )
            ORDER BY cs.created_at DESC
            LIMIT 10
        """).fetchall()

        generated = 0
        for r in rows:
            cid = r["cluster_id"]
            import os
            if os.path.exists(f"static/generated/{cid}.jpg"):
                # Already generated but not linked — link it
                conn.execute(
                    "UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 1)",
                    (f"/static/generated/{cid}.jpg", cid)
                )
                conn.commit()
                generated += 1
                continue

            img_url = generate_cover_art(cid, r["summary"])
            if img_url:
                conn.execute(
                    "UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 1)",
                    (img_url, cid)
                )
                conn.commit()
                generated += 1
                time.sleep(2)  # Be nice to free API

        if generated:
            log.info(f"[backfill] Generated cover art for {generated} clusters")
    except Exception as e:
        log.error(f"[backfill] Cover art backfill failed: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task
def run_prune_db():
    """Periodic task to prune old articles and clean up files."""
    log.info("Pruning old database entries...")
    prune_db()
    log.info("Cleaning up orphaned cover art...")
    cleanup_cover_art_task.delay()

@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3)
def translate_article_task(article_id: int, original_title: str, original_description: str):
    """Background task to translate diaspora articles."""
    conn = None
    try:
        conn = get_db()

        translated_title = original_title
        if original_title:
            try:
                result = translate_to_macedonian(original_title)
                if result is not None:
                    translated_title = result
            except Exception as e:
                log.error(f"Translation error (title) for {article_id}: {e}")

        translated_desc = original_description
        if original_description:
            try:
                result = translate_to_macedonian(original_description)
                if result is not None:
                    translated_desc = result
            except Exception as e:
                log.error(f"Translation error (desc) for {article_id}: {e}")

        cur = conn.cursor()
        cur.execute(
            "UPDATE articles SET title = %s, description = %s, is_translated = 1 WHERE id = %s",
            (translated_title, translated_desc, article_id)
        )
        conn.commit()
        cur.close()
    except Exception as e:
        log.error(f"Task failed for article {article_id}: {e}")
    finally:
        if conn:
            conn.close()

@celery_app.task
def send_telegram_briefing_task():
    """Sends today's briefing to Telegram via OpenClaw (primary) or Bot API (fallback)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    conn = None
    try:
        conn = get_db()
        today = datetime.date.today()
        row = conn.execute("SELECT content FROM daily_briefings WHERE date = %s", (today,)).fetchone()
        if not row:
            log.warning(f"[telegram] No briefing found for {today}")
            return
            
        content = row["content"]
        # Markdown for Bot API, HTML for OpenClaw (as per user script)
        # Let's use a dual-safe format or adjust per method
        
        # 1. Try OpenClaw Gateway First
        if OPENCLAW_URL and OPENCLAW_TOKEN:
            try:
                import requests
                # OpenClaw uses HTML by default in the user script
                html_text = f"<b>🗞 Дневен Брифинг — {today.strftime('%d.%m.%Y')}</b>\n\n{content}\n\n🔗 Прочитај повеќе на <a href='https://presek.mk'>presek.mk</a>"
                endpoint = f"{OPENCLAW_URL.rstrip('/')}/channels/presekmk/message"
                headers = {"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"}
                payload = {"text": html_text, "parse_mode": "HTML"}
                
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    log.info(f"[openclaw] Briefing sent successfully.")
                    return
                log.warning(f"[openclaw] Gateway returned {resp.status_code}, falling back to Bot API.")
            except Exception as e:
                log.warning(f"[openclaw] Gateway failed: {e}, falling back to Bot API.")

        # 2. Fallback: Direct Telegram Bot API
        import urllib.parse
        md_text = f"🗞 *Дневен Брифинг — {today.strftime('%d.%m.%Y')}*\n\n{content}\n\n🔗 Прочитај повеќе на [presek.mk](https://presek.mk)"
        encoded_text = urllib.parse.quote(md_text)
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={encoded_text}&parse_mode=Markdown"
        
        with urllib.request.urlopen(url, timeout=10) as resp:
            log.info(f"[telegram-bot] Briefing sent successfully.")
            
    except Exception as e:
        log.error(f"[telegram] All delivery methods failed: {e}")
    finally:
        if conn:
            conn.close()
