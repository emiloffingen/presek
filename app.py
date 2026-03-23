from __future__ import annotations
import datetime, json, os, sqlite3, threading, time, urllib.request, urllib.error, feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from collections import defaultdict

import health
import trending
import clustering
from categories import detect_category, detect_subcategory, detect_country
from notifier import BreakingNewsNotifier
import digest as digest_module

from functools import lru_cache
import hashlib

# Simple time-based response cache
_response_cache: dict[str, tuple[float, any]] = {}

def cached_response(key: str, ttl: int = 60):
    """Return cached value if fresh, else None."""
    if key in _response_cache:
        ts, val = _response_cache[key]
        if time.time() - ts < ttl:
            return val
    return None

def set_cache(key: str, val):
    """Store value in cache with current timestamp."""
    _response_cache[key] = (time.time(), val)

# Simple rate limiter
_rate_limits: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60     # requests per window

def check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate limited."""
    now = time.time()
    if ip not in _rate_limits:
        _rate_limits[ip] = []
    # Clean old entries
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[ip].append(now)
    return True

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),                         # screen output
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "presek.log"),
            encoding="utf-8"
        ),
    ]
)
log = logging.getLogger("presek")

app = Flask(__name__)
CORS(app)
from flask_compress import Compress
Compress(app)

@app.before_request
def rate_limit_check():
    # Skip rate limiting for static files and the main page
    if request.path in ('/', '/favicon.ico') or request.path.startswith('/static'):
        return None
    ip = request.remote_addr or '0.0.0.0'
    if not check_rate_limit(ip):
        return jsonify({"error": "Премногу барања. Обидете се повторно."}), 429

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "presek.db"))
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "presek-mk-vesti")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

REFRESH_INTERVAL = 900
FEED_LIMIT = 10
CLUSTER_LOOKBACK = 500  # increased from 200 — handles 36 sources × 10 entries per refresh

# In-memory cache for cluster-wide AI summaries (persists until process restart)
_cluster_summary_cache: dict[str, str] = {}

RSS_FEEDS = [
    # ── Original 10 ──────────────────────────────────────────────
    ("Sloboden Pecat",  "https://slobodenpecat.mk/feed/"),
    ("Kanal 5",         "https://kanal5.com.mk/feed/"),
    ("MIA",             "https://mia.mk/mk/rss"),
    ("Sitel",           "https://sitel.com.mk/rss.xml"),
    ("Telma",           "https://telma.com.mk/feed/"),
    ("Kurir",           "https://kurir.mk/feed/"),
    ("Republika",       "https://republika.mk/feed/"),
    ("Fokus",           "https://fokus.mk/feed/"),
    ("Nezavisen",       "https://nezavisen.mk/feed/"),
    ("Faktor",          "https://faktor.mk/rss"),
    # ── Batch 2 ──────────────────────────────────────────────────
    ("Vecer",           "https://vecer.mk/feed/"),
    ("Meta",            "https://meta.mk/feed/"),
    ("360 Stepeni",     "https://360stepeni.mk/feed/"),
    ("Makfax",          "https://makfax.com.mk/feed/"),
    ("Nova Makedonija", "https://novamakedonija.com.mk/feed/"),
    ("Infomax",         "https://infomax.mk/feed/"),
    # ── Batch 3 ──────────────────────────────────────────────────
    ("Press24",         "https://press24.mk/feed/"),
    ("Skopje1",         "https://skopje1.mk/feed/"),
    ("Plusinfo",        "https://plusinfo.mk/feed/"),
    ("Lokalno",         "https://lokalno.mk/feed/"),
    ("4News",           "https://4news.mk/feed/"),
    ("Makpress",        "https://makpress.mk/feed/"),
    ("Vistinomer",      "https://vistinomer.mk/feed/"),
    ("Portalb",         "https://portalb.mk/feed/"),
    ("Lider",           "https://lider.mk/feed/"),
    ("MKD",             "https://mkd.mk/feed/"),
    ("NetPress",        "https://netpress.com.mk/feed/"),
    ("Akademik",        "https://akademik.mk/feed/"),
    ("Skopje Info",     "https://skopjeinfo.mk/feed/"),
    ("Prizma",          "https://prizma.mk/feed/"),
    ("Expres",          "https://expres.mk/feed/"),
    ("Tetovo Info",     "https://tetovoinfo.mk/feed/"),
    ("Koha",            "https://koha.mk/feed/"),
    ("A1on",            "https://a1on.mk/feed/"),
    ("SportSport",      "https://sportsport.mk/feed/"),
    ("Strumica Info",   "https://strumicainfo.mk/feed/"),
    # ── Batch 4 — sourced from time.mk index ─────────────────────
    ("24 Вести",        "https://24.mk/feed/"),
    ("TV21",            "https://tv21.mk/feed/"),
    ("Слободна Европа", "https://www.slobodnaevropa.mk/api/zryoyqpmou"),
    ("Deutsche Welle",  "https://feeds.dw.com/rss/rss-mac-all"),
    ("Журнал",          "https://zurnal.mk/feed/"),
    ("Civil Media",     "https://civil.mk/feed/"),
    ("Радио МОФ",       "https://radiomof.mk/feed/"),
    ("Сакам да кажам",  "https://sdk.mk/feed/"),
    ("Бизнис Вести",    "https://biznisvesti.mk/feed/"),
    # ── Batch 5 — additional quality sources ─────────────────────
    ("Ohrid News",      "https://ohridnews.mk/feed/"),
    ("Vecer Sport",     "https://sport.vecer.mk/feed/"),
    ("Ekonomija",       "https://ekonomija.com.mk/feed/"),
    ("Zdravje",         "https://zdravje.com.mk/feed/"),
    ("MRT",             "https://mrt.com.mk/feed/"),
    ("Time.mk",         "https://time.mk/rss"),
    ("Kolumna",         "https://kolumna.mk/feed/"),
    ("Okno",            "https://okno.mk/feed/"),
    ("Alfa TV",         "https://alfa.mk/feed/"),
    ("Tocka",           "https://tocka.com.mk/feed/"),
]

DIASPORA_FEEDS = [
    # 🇩🇪 Germany
    ("Tagesschau",  "https://www.tagesschau.de/xml/rss2",                                       "Свет"),
    ("Der Spiegel", "https://www.spiegel.de/schlagzeilen/index.rss",                            "Свет"),
    # 🇨🇭 Switzerland
    ("SRF News",    "https://www.srf.ch/news/bnf/rss/1890",                                     "Свет"),
    ("20 Minuten",  "https://www.20min.ch/rss/rss.tmpl?type=channel&get=4",                     "Свет"),
    # 🇺🇸 USA
    ("CNN",         "http://rss.cnn.com/rss/cnn_topstories.rss",                                 "Свет"),
    ("NPR",         "https://feeds.npr.org/1001/rss.xml",                                        "Свет"),
    ("Reuters",     "https://www.reutersagency.com/feed/",                                       "Свет"),
    # 🇨🇦 Canada
    ("CBC News",    "https://rss.cbc.ca/lineup/topstories.xml",                                  "Свет"),
    # 🇬🇧 United Kingdom
    ("BBC News",    "https://feeds.bbci.co.uk/news/rss.xml",                                     "Свет"),
    ("The Guardian", "https://www.theguardian.com/world/rss",                                    "Свет"),
    # 🇦🇺 Australia
    ("ABC Australia", "https://www.abc.net.au/news/feed/2942460/rss.xml",                        "Свет"),
    # 🇮🇹 Italy
    ("ANSA",        "https://www.ansa.it/sito/ansait_rss.xml",                                   "Свет"),
    # 🇷🇸 Serbia / Region
    ("N1 Info",     "https://n1info.rs/feed/",                                                   "Регион"),
    ("B92",         "https://www.b92.net/info/rss/vesti.xml",                                    "Регион"),
    # 🇷🇸 Serbia — high readership in Macedonia
    ("Kurir.rs",     "https://www.kurir.rs/rss",                                                 "Регион"),
    ("Blic.rs",      "https://www.blic.rs/rss",                                                  "Регион"),
    # 🇧🇬 Bulgaria
    ("Novinite",    "https://www.novinite.com/rss.php",                                          "Регион"),
    # 🇬🇷 Greece
    ("Kathimerini", "https://www.ekathimerini.com/rss",                                          "Регион"),
    # 🇦🇱 Albania / Kosovo
    ("Exit News",   "https://exit.al/en/feed/",                                                  "Регион"),
    # 🇽🇰 Kosovo
    ("Telegrafi",    "https://telegrafi.com/feed/",                                              "Регион"),
    # 🇹🇷 Turkey
    ("Daily Sabah",  "https://www.dailysabah.com/rssFeed/politics",                              "Свет"),
    ("TRT World",    "https://www.trtworld.com/content/rss.xml",                                 "Свет"),
    # 🌍 Balkans investigative
    ("Balkan Insight", "https://balkaninsight.com/feed/",                                        "Регион"),
]

# ── Source credibility weights (PageRank-style) ──────────────────
# Scale: 1.0 = baseline, higher = more authoritative
# Major national outlets score higher; aggregators/local portals lower
SOURCE_CREDIBILITY = {
    "MIA":              2.0,  # state news agency — primary source
    "MRT":              1.8,  # national public broadcaster
    "Sitel":            1.7,  # major national TV
    "Kanal 5":          1.7,  # major national TV
    "Telma":            1.6,  # major national TV
    "Alfa TV":          1.5,
    "Sloboden Pecat":   1.5,  # established print/online
    "Nova Makedonija":  1.5,  # oldest daily newspaper
    "Republika":        1.4,
    "Makfax":           1.4,  # established wire service
    "Fokus":            1.3,
    "Nezavisen":        1.3,
    "Kurir":            1.2,
    "Faktor":           1.2,
    "Vecer":            1.2,
    "Meta":             1.2,
    "360 Stepeni":      1.1,
    "Infomax":          1.1,
    "Lider":            1.1,
    "Vistinomer":       1.8,  # fact-checking outlet — boost
    "Birn":             1.3,  # regional investigative journalism
    "Akademik":         1.1,
    "NetPress":         1.0,
    "Portalb":          1.0,
    "MKD":              1.0,
    "Press24":          0.9,
    "Skopje1":          0.9,
    "Plusinfo":          0.9,
    "Lokalno":          0.9,
    "4News":            0.9,
    "Makpress":         0.9,
    "Skopje Info":      0.8,
    "Prizma":           0.8,
    "Expres":           0.8,
    "Tetovo Info":      0.8,
    "Koha":             0.8,
    "A1on":             0.8,
    "SportSport":       0.8,
    "Strumica Info":    0.8,
    # Batch 4
    "24 Вести":         1.6,  # major national TV
    "TV21":             1.6,  # major national TV
    "Слободна Европа":  1.8,  # RFE/RL — internationally funded, editorially independent
    "Deutsche Welle":   1.7,  # international public broadcaster, MK edition
    "Журнал":           1.2,
    "Civil Media":      1.3,  # independent civil society media
    "Радио МОФ":        1.1,  # youth/independent online radio
    "Сакам да кажам":   1.1,
    "Бизнис Вести":     1.0,
    # Batch 5
    "Ohrid News":       0.8,
    "Vecer Sport":      1.0,
    "Ekonomija":        0.9,
    "Zdravje":          0.8,
    "Time.mk":          1.1,
    "Kolumna":          0.9,
    "Okno":             1.0,
    # Diaspora & Regional
    "Tagesschau":       1.8,  # German public broadcaster
    "Der Spiegel":      1.7,  # major German weekly
    "SRF News":         1.7,  # Swiss public broadcaster
    "20 Minuten":       1.2,  # Swiss tabloid
    "CNN":              1.6,  # major US cable news
    "NPR":              1.6,  # US public radio
    "Reuters":          1.9,  # global wire service
    "CBC News":         1.7,  # Canadian public broadcaster
    "BBC News":         1.8,  # British public broadcaster
    "The Guardian":     1.7,  # major UK broadsheet
    "ABC Australia":    1.6,  # Australian public broadcaster
    "ANSA":             1.6,  # Italian wire service
    "N1 Info":          1.5,  # regional independent TV (Serbia/Balkans)
    "B92":              1.4,  # Serbian news
    "Novinite":         1.2,  # Bulgarian English-language news
    "Kathimerini":      1.5,  # major Greek daily
    "Exit News":        1.3,  # Albanian independent news
    "Alfa TV":          1.5,
    "Telegrafi":        1.3,
    "Daily Sabah":      1.4,
    "TRT World":        1.6,
    "Balkan Insight":   1.7,
    "Tocka":            1.1,
    "Kurir.rs":         1.2,
    "Blic.rs":          1.3,
}
DEFAULT_CREDIBILITY = 0.8  # fallback for unlisted sources

# Breaking news threshold — score above this gets a 🔴 badge in the UI
BREAKING_SCORE_THRESHOLD = 3.0
DB_RETAIN_DAYS = 14  # articles older than this are pruned daily

ntfy = BreakingNewsNotifier(topic=NTFY_TOPIC, threshold=3)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_feed(source, url):
    """Fetch a single RSS feed. Returns list of (title, link, desc, image_url) tuples."""
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "Presek.mk/1.0"})
        entries = []
        for entry in feed.entries[:FEED_LIMIT]:
            title = getattr(entry, "title", "").strip()
            link  = getattr(entry, "link",  "").strip()
            desc  = getattr(entry, "summary", "")
            
            # --- Image Extraction Logic ---
            image_url = ""
            # 1. media:content
            if not image_url and hasattr(entry, 'media_content') and entry.media_content:
                for m in entry.media_content:
                    u = m.get('url', '')
                    if u and any(ext in u.lower() for ext in ['.jpg','.jpeg','.png','.webp','.gif']):
                        image_url = u; break
                if not image_url:
                    image_url = entry.media_content[0].get('url', '')
            # 2. enclosure
            if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
                for enc in entry.enclosures:
                    if 'image' in enc.get('type','') or any(ext in enc.get('url','').lower() for ext in ['.jpg','.jpeg','.png','.webp']):
                        image_url = enc.get('url',''); break
            # 3. links with image type
            if not image_url and hasattr(entry, 'links'):
                for link_obj in entry.links:
                    if 'image' in link_obj.get('type', ''):
                        image_url = link_obj.get('href', ''); break
            # 4. <img> in description HTML
            if not image_url and desc:
                import re as _re
                m = _re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc, _re.IGNORECASE)
                if m:
                    c = m.group(1)
                    if not any(s in c.lower() for s in ['pixel','icon','1x1','logo','gravatar','avatar']):
                        image_url = c
            # 5. media:thumbnail
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
    recent_rows = conn.execute(
        "SELECT title, cluster_id FROM articles ORDER BY created_at DESC LIMIT ?",
        (CLUSTER_LOOKBACK,)
    ).fetchall()
    recent_articles = [{"title": r["title"], "cluster_id": r["cluster_id"]} for r in recent_rows]

    # ── Phase 1: fetch all feeds in parallel ─────────────────────
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

    # ── Phase 2: write to DB sequentially (no lock contention) ───
    new_count = 0
    for source, title, link, desc, image_url in all_entries:
        try:
            if conn.execute("SELECT id FROM articles WHERE link = ?", (link,)).fetchone():
                continue
            category   = detect_category(title, description=desc, source=source)
            subcategory = detect_subcategory(title, description=desc) or ""
            cluster_id = clustering.find_or_create_cluster(title, recent_articles)
            now        = datetime.datetime.now().isoformat()
            # Strip HTML tags from description for clean storage
            import re as _re
            clean_desc = _re.sub(r'<[^>]+>', '', desc).strip()[:500] if desc else ""
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
    conn.close()
    return new_count, errors


def translate_titles_batch(titles: list[str]) -> list[str]:
    """Translate a list of titles to Macedonian using small batches.
    Returns list same length as input. Untranslated items are set to None
    so the caller can skip them."""
    if not titles or not GOOGLE_API_KEY:
        return [None] * len(titles)

    BATCH_SIZE = 10
    result = [None] * len(titles)
    import re as _re

    for start in range(0, len(titles), BATCH_SIZE):
        batch = titles[start:start + BATCH_SIZE]
        titles_json = json.dumps(batch, ensure_ascii=False)
        prompt = (
            "Преведи ги овие наслови на македонски јазик. "
            "Врати JSON листа со преводите во ист редослед. "
            "Само преводите, без објаснувања.\n\n" + titles_json
        )
        translated = None
        for attempt in range(2):  # retry once
            raw = _call_gemini(prompt, "Ти си професионален преведувач на македонски јазик.", timeout=20)
            if not raw:
                time.sleep(2)
                continue
            try:
                clean = _re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
                m = _re.search(r'\[[\s\S]*\]', clean)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, list) and len(parsed) == len(batch):
                        translated = [str(t) for t in parsed]
                        break
            except Exception as e:
                log.warning(f"[diaspora] Translation parse failed: {e}")
            time.sleep(1)

        if translated:
            for i, t in enumerate(translated):
                result[start + i] = t
        else:
            log.warning(f"[diaspora] Translation failed for batch starting at {start}, skipping {len(batch)} articles")

        if start + BATCH_SIZE < len(titles):
            time.sleep(1.5)  # rate limit between batches

    return result


def ingest_diaspora_feeds():
    """Fetch diaspora RSS feeds, batch-translate titles, write to DB separately."""
    conn = get_db()
    diaspora_recent = conn.execute(
        "SELECT title, cluster_id FROM articles WHERE country != '🇲🇰' ORDER BY created_at DESC LIMIT ?",
        (CLUSTER_LOOKBACK,)
    ).fetchall()
    diaspora_recent = [{"title": r["title"], "cluster_id": r["cluster_id"]} for r in diaspora_recent]
    conn.close()

    # Build source → (category, country) lookup
    feed_meta = {s: (cat, detect_country(s)) for s, u, cat in DIASPORA_FEEDS}

    # Phase 1: fetch all feeds in parallel
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

    # Phase 2: batch-translate all titles in one API call
    titles = [e[1] for e in all_entries]
    translated = translate_titles_batch(titles)

    # Phase 3: write to DB sequentially
    import re as _re
    conn = get_db()
    new_count = 0
    for i, (source, title, link, desc, image_url, category, country) in enumerate(all_entries):
        try:
            if conn.execute("SELECT id FROM articles WHERE link = ?", (link,)).fetchone():
                continue
            mk_title = translated[i] if i < len(translated) else None
            if mk_title is None:
                continue  # skip untranslated — will be picked up next cycle
            cluster_id = clustering.find_or_create_cluster(mk_title, diaspora_recent)
            now = datetime.datetime.now().isoformat()
            clean_desc = _re.sub(r'<[^>]+>', '', desc).strip()[:500] if desc else ""
            conn.execute(
                "INSERT INTO articles "
                "(title, original_title, link, source, category, subcategory, cluster_id, "
                "created_at, image_url, description, country) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mk_title, title, link, source, category, "", cluster_id,
                 now, image_url, clean_desc, country)
            )
            diaspora_recent.insert(0, {"title": mk_title, "cluster_id": cluster_id})
            if len(diaspora_recent) > CLUSTER_LOOKBACK:
                diaspora_recent.pop()
            new_count += 1
        except Exception as e:
            log.error(f"[diaspora] DB write error — {source} | {title[:40]}: {e}")

    conn.commit()
    conn.close()
    return new_count, errors


def prune_db():
    """Delete articles older than DB_RETAIN_DAYS and reclaim disk space."""
    try:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=DB_RETAIN_DAYS)).isoformat()
        conn = get_db()
        result = conn.execute("DELETE FROM articles WHERE created_at < ?", (cutoff,))
        deleted = result.rowcount
        conn.execute("VACUUM")
        conn.commit()
        conn.close()
        if deleted:
            log.info(f"Pruned {deleted} articles older than {DB_RETAIN_DAYS} days.")
    except Exception as e:
        log.error(f"Prune error: {e}")

_prune_counter = 0
_digest_counter = 0

# ── Auto-summarization settings ──────────────────────────────────
AUTO_SUMMARIZE_TOP_N   = 5    # summarize the top N clusters each cycle
AUTO_SUMMARIZE_MIN_SRC = 2    # only clusters with 2+ sources get synthesis
AUTO_SUMMARIZE_DELAY   = 1.5  # seconds between API calls (rate limit protection)


def _call_gemini(prompt_text: str, system_prompt: str, timeout: int = 25) -> str | None:
    """Shared Gemini caller for auto-summarization. Returns None on failure."""
    if not GOOGLE_API_KEY:
        return None
    try:
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": prompt_text}]}]
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{GEMINI_URL}?key={GOOGLE_API_KEY}",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log.warning(f"[auto-summarize] Gemini call failed: {e}")
        return None


def _call_ai(prompt_text: str, system_prompt: str) -> tuple[str | None, str | None]:
    """Call Gemini API. Returns (summary, 'gemini') or (None, None)."""
    result = _call_gemini(prompt_text, system_prompt)
    if result:
        return result, "gemini"
    return None, None


def auto_summarize_top_clusters():
    """
    Automatically summarize the top clusters after each ingest cycle.
    - Generates a cluster synthesis for multi-source clusters
    - Generates an article summary for the lead article of top clusters
    Runs in the ingest thread, respects rate limits with delays.
    """
    if not GOOGLE_API_KEY:
        return  # no Gemini key, skip silently

    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM articles WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
        conn.close()
    except Exception as e:
        log.error(f"[auto-summarize] DB read failed: {e}")
        return

    if not rows:
        return

    # Build clusters and rank them
    clusters_map = defaultdict(list)
    for r in rows:
        clusters_map[r["cluster_id"]].append(dict(r))

    ranked = []
    for cid, arts in clusters_map.items():
        sorted_arts = rank_articles_in_cluster(arts)
        s = score_cluster(sorted_arts)
        ranked.append((cid, sorted_arts, s))
    ranked.sort(key=lambda x: x[2], reverse=True)

    top = ranked[:AUTO_SUMMARIZE_TOP_N]
    summarized_count = 0
    synthesis_count = 0

    for cid, arts, score in top:
        lead = arts[0]

        # 1. Summarize the lead article (if not already done)
        if not lead.get("summary"):
            summary, tier = _call_ai(lead["title"], SUMMARY_SYSTEM_PROMPT)
            if summary:
                try:
                    conn = get_db()
                    conn.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, lead["id"]))
                    conn.commit()
                    conn.close()
                    summarized_count += 1
                except Exception as e:
                    log.warning(f"[auto-summarize] DB write failed for article {lead['id']}: {e}")
                time.sleep(AUTO_SUMMARIZE_DELAY)

        # 2. Generate cluster synthesis (if multi-source and not cached)
        unique_sources = {a["source"] for a in arts}
        if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC and cid not in _cluster_summary_cache:
            headlines = "\n".join(
                f"- [{a['source']}]: {a['title']}"
                for a in arts[:10]
            )
            synthesis, tier = _call_ai(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT)
            if synthesis:
                _cluster_summary_cache[cid] = synthesis
                synthesis_count += 1
                time.sleep(AUTO_SUMMARIZE_DELAY)

    if summarized_count or synthesis_count:
        log.info(f"[auto-summarize] {summarized_count} article summaries, {synthesis_count} cluster syntheses generated.")

def ingest_loop():
    while True:
        try:
            log.info("Fetching RSS feeds...")
            new_count, errors = ingest_feeds()
            health.record_refresh(new_count, errors)
            log.info(f"Added {new_count} new articles, {len(errors)} errors.")
            diaspora_count, diaspora_errors = ingest_diaspora_feeds()
            log.info(f"[diaspora] Added {diaspora_count} articles, {len(diaspora_errors)} errors.")
            global _prune_counter
            _prune_counter += 1
            if _prune_counter >= 96:
                prune_db()
                _prune_counter = 0
            global _digest_counter
            _digest_counter += 1
            if _digest_counter >= 96:
                try:
                    digest_module.generate_digest(
                        db_path=DB_PATH,
                        days=1,
                        save_path=os.path.expanduser("~/presek/digests/digest.html"),
                        ntfy_topic=NTFY_TOPIC,
                    )
                except Exception as _de:
                    log.error(f"Digest failed: {_de}")
                _digest_counter = 0
            
            conn = get_db()
            rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT 500").fetchall()
            conn.close()
            cmap = defaultdict(list)
            for r in rows: cmap[r["cluster_id"]].append(dict(r))
            ntfy.check_and_notify([{"cluster_id": cid, "articles": arts} for cid, arts in cmap.items()])

            # Auto-summarize top clusters with AI
            auto_summarize_top_clusters()
            
        except Exception as e:
            log.error(f"Ingest loop failed: {e}", exc_info=True)
        time.sleep(REFRESH_INTERVAL)

health.register_health_routes(app, DB_PATH)
trending.register_trending_route(app, DB_PATH)

def score_cluster(arts):
    """
    PageRank-style cluster importance score.
    Combines:
      - Source count (breadth of coverage)
      - Credibility-weighted source score
      - Recency (decays over 24h)
    """
    import math
    now = datetime.datetime.now()

    # Credibility score — sum of weights of unique sources
    unique_sources = {a["source"] for a in arts}
    cred_score = sum(
        SOURCE_CREDIBILITY.get(s, DEFAULT_CREDIBILITY)
        for s in unique_sources
    )

    # Recency score — exponential decay, half-life = 6 hours
    try:
        latest = datetime.datetime.fromisoformat(arts[0]["created_at"].replace("+00:00", ""))
        hours_old = (now - latest).total_seconds() / 3600
    except Exception:
        hours_old = 24
    recency = math.exp(-0.115 * hours_old)  # e^(-ln2/6 * h) ≈ halves every 6h

    # Source count bonus (logarithmic — diminishing returns)
    breadth = math.log1p(len(arts))

    # Click engagement bonus
    total_clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    click_bonus = 1 + math.log1p(total_clicks) * 0.15

    return cred_score * recency * breadth * click_bonus


def rank_articles_in_cluster(arts):
    """Within a cluster, put the most credible source first."""
    return sorted(
        arts,
        key=lambda a: SOURCE_CREDIBILITY.get(a["source"], DEFAULT_CREDIBILITY),
        reverse=True
    )


@app.route("/api/news")
def api_news():
    page      = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    page_size = min(page_size, 100)  # cap at 100
    cache_key = f"news:{page}:{page_size}"
    cached = cached_response(cache_key, ttl=30)
    if cached:
        return jsonify(cached)
    # Fetch more than needed to form clusters, then paginate the result
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    conn.close()

    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))

    # Within each cluster: most credible source first
    ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]

    # Across clusters: PageRank score determines feed order
    sorted_clusters = sorted(ranked_clusters, key=score_cluster, reverse=True)

    # Return structured objects so frontend can use score for breaking badge
    result = []
    for arts in sorted_clusters:
        s   = score_cluster(arts)
        cid = arts[0]["cluster_id"] if arts else None
        result.append({
            "articles":      arts,
            "score":         round(s, 3),
            "cluster_id":    cid,
            "is_breaking":   s >= BREAKING_SCORE_THRESHOLD,
            "has_summary":   any(a.get("summary") for a in arts),
            "has_synthesis": cid in _cluster_summary_cache,
        })

    # Paginate the ranked cluster list
    start  = page * page_size
    end    = start + page_size
    paged  = result[start:end]
    result_data = {
        "clusters":    paged,
        "page":        page,
        "page_size":   page_size,
        "total":       len(result),
        "has_more":    end < len(result),
    }
    set_cache(cache_key, result_data)
    return jsonify(result_data)


@app.route("/api/scores")
def api_scores():
    """Debug endpoint — shows PageRank scores for current top clusters."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT 250").fetchall()
    conn.close()
    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))
    result = []
    for arts in clusters.values():
        arts = rank_articles_in_cluster(arts)
        result.append({
            "headline": arts[0]["title"][:60],
            "sources": [a["source"] for a in arts],
            "score": round(score_cluster(arts), 3),
        })
    result.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(result[:20])


SUMMARY_SYSTEM_PROMPT = (
    "Ти си професионален уредник на македонска новинска агенција. "
    "Даден ти е наслов на вест на македонски јазик. "
    "Одговори ИСКЛУЧИВО на стандарден литературен македонски јазик. НЕ користи српски, хрватски или бугарски зборови. "
    "САМО во овој формат без никаков додатен текст:\n"
    "Ред 1: Сентимент — точно еден емоџи: 🟢 (позитивно) или 🔴 (негативно) или ⚪ (неутрално)\n"
    "Ред 2-3: Две кратки, фактички реченици кои го објаснуваат контекстот. Отстрани секаков сензационализам и кликбејт.\n"
    "Ред 4: Три до пет клучни зборови со # (пример: #Скопје #Влада #Буџет)\n"
    "Важно: Не пишувај воведни фрази, наслови, или објаснувања. Само форматот."
)

SYNTHESIS_SYSTEM_PROMPT = (
    "Ти си искусен уредник на македонска новинска агенција. "
    "Дадени ти се наслови за иста вест од различни медиуми. "
    "Одговори ИСКЛУЧИВО на стандарден литературен македонски јазик. НЕ користи српски, хрватски или бугарски зборови. "
    "САМО во овој формат без никаков додатен текст:\n"
    "Ред 1: Сентимент — точно еден емоџи: 🟢 (позитивно) или 🔴 (негативно) или ⚪ (неутрално)\n"
    "Ред 2-4: Две до три фактички реченици — синтеза на сите перспективи. Ако изворите се разликуваат, наведи ја разликата "
    "(пример: 'Извор А тврди X, додека Извор Б тврди Y'). Биди неутрален и конкретен. "
    "Ако насловите содржат конфликтни податоци (различни бројки, спротивни тврдења за одговорност), "
    "започни со '⚠️ Разлика:' и именувај ги изворите. \n"
    "Ред 5: Три до пет клучни зборови со # (пример: #Македонија #Политика #ВМРО)\n"
    "Важно: Не пишувај воведни фрази. Само форматот."
)



@app.route("/api/summarize/<int:article_id>")
def api_summarize(article_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Article not found"}), 404
    if row["summary"]:
        conn.close()
        return jsonify({"summary": row["summary"], "cached": True})

    summary, tier = _call_ai(row["title"], SUMMARY_SYSTEM_PROMPT)

    if not summary:
        conn.close()
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    conn.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    conn.commit()
    conn.close()
    return jsonify({"summary": summary, "cached": False, "tier": tier})


@app.route("/api/cluster-summary/<cluster_id>")
def api_cluster_summary(cluster_id: str):
    """
    Cluster-wide AI synthesis — feeds all articles in a cluster to Gemini
    and returns a cross-source summary with multiple perspectives.
    Results are cached in memory for the lifetime of the process.
    """
    if cluster_id in _cluster_summary_cache:
        return jsonify({"summary": _cluster_summary_cache[cluster_id], "cached": True})

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at ASC LIMIT 10",
        (cluster_id,)
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": "Cluster not found"}), 404

    articles = [dict(r) for r in rows]
    headlines = "\n".join(
        f"- [{a['source']}]: {a['title']}"
        for a in articles
    )

    summary, tier = _call_ai(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT)

    if not summary:
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    _cluster_summary_cache[cluster_id] = summary
    return jsonify({"summary": summary, "source_count": len(articles), "cached": False, "tier": tier})




@app.route("/api/click/<int:article_id>", methods=["POST"])
def api_click(article_id: int):
    """Increment click counter for an article."""
    try:
        conn = get_db()
        conn.execute("UPDATE articles SET clicks = COALESCE(clicks,0) + 1 WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/popular")
def api_popular():
    """Return most-clicked clusters in the last 7 days."""
    cached = cached_response("popular", ttl=120)
    if cached:
        return jsonify(cached)
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE created_at >= datetime('now', '-7 days')
        AND clicks > 0
        ORDER BY clicks DESC LIMIT 200
    """).fetchall()
    conn.close()
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    sorted_clusters = sorted(ranked, key=lambda arts: sum(a.get("clicks",0) for a in arts), reverse=True)
    result = []
    for arts in sorted_clusters[:20]:
        result.append({
            "articles":    arts,
            "score":       round(score_cluster(arts), 3),
            "cluster_id":  arts[0]["cluster_id"],
            "total_clicks": sum(a.get("clicks",0) for a in arts),
            "is_breaking": False,
        })
    set_cache("popular", result)
    return jsonify(result)


@app.route("/api/timeboxed")
def api_timeboxed():
    """Return top clusters for each time window: утро 6-12, попладне 12-18, вечер 18-24."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    conn.close()

    from collections import defaultdict
    import datetime as _dt

    def window_for(ts):
        try:
            dt = _dt.datetime.fromisoformat(ts.replace("+00:00",""))
            h  = dt.hour
            if 6  <= h < 12: return "утро"
            if 12 <= h < 18: return "попладне"
            if 18 <= h < 24: return "вечер"
            return "ноќ"
        except Exception:
            return "ноќ"

    windows = {"утро": defaultdict(list), "попладне": defaultdict(list), "вечер": defaultdict(list)}

    for r in rows:
        w = window_for(r["created_at"])
        if w in windows:
            windows[w][r["cluster_id"]].append(dict(r))

    result = {}
    for w, clusters in windows.items():
        ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        sorted_c = sorted(ranked, key=score_cluster, reverse=True)[:20]
        result[w] = []
        for arts in sorted_c:
            s = score_cluster(arts)
            result[w].append({
                "articles":    arts,
                "score":       round(s, 3),
                "cluster_id":  arts[0]["cluster_id"] if arts else None,
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
            })

    return jsonify(result)

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE title LIKE ? OR source LIKE ? ORDER BY created_at DESC LIMIT 200",
        (f"%{q}%", f"%{q}%")
    ).fetchall()
    conn.close()
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    sorted_clusters = sorted(ranked, key=score_cluster, reverse=True)
    result = []
    for arts in sorted_clusters:
        s = score_cluster(arts)
        result.append({
            "articles":    arts,
            "score":       round(s, 3),
            "cluster_id":  arts[0]["cluster_id"] if arts else None,
            "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
        })
    return jsonify(result)


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/sw.js")
def service_worker():
    from flask import Response, send_from_directory
    resp = send_from_directory(
        os.path.dirname(os.path.abspath(__file__)), "sw.js"
    )
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp



@app.route("/izvori")
def izvori_page():
    return render_template("izvori.html", year=__import__('datetime').datetime.now().year)

@app.route("/stats")
def stats_page():
    return render_template("stats.html", year=__import__('datetime').datetime.now().year)


@app.route("/api/stats/full")
def api_stats_full():
    """Extended stats including feed errors, click data, and DB size."""
    import os as _os
    try:
        conn = get_db()
        total      = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        by_cat     = conn.execute("SELECT category, COUNT(*) n FROM articles GROUP BY category ORDER BY n DESC").fetchall()
        by_source  = conn.execute("SELECT source, COUNT(*) n FROM articles GROUP BY source ORDER BY n DESC").fetchall()
        recent_24h = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= datetime('now','-1 day')").fetchone()[0]
        recent_7d  = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= datetime('now','-7 days')").fetchone()[0]
        summarized = conn.execute("SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''").fetchone()[0]
        top_clicks = conn.execute("""
            SELECT title, source, clicks, link FROM articles
            WHERE clicks > 0 ORDER BY clicks DESC LIMIT 10
        """).fetchall()
        oldest     = conn.execute("SELECT MIN(created_at) FROM articles").fetchone()[0]
        newest     = conn.execute("SELECT MAX(created_at) FROM articles").fetchone()[0]
        conn.close()

        db_size = _os.path.getsize(DB_PATH) / (1024*1024)  # MB

        import time as _time
        uptime_s = int(_time.time() - health._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, _   = divmod(rem, 60)

        return jsonify({
            "uptime": f"{h}ч {m}м",
            "db_size_mb": round(db_size, 2),
            "total_articles": total,
            "last_24h": recent_24h,
            "last_7d": recent_7d,
            "summarized": summarized,
            "summarized_pct": round(summarized / total * 100, 1) if total else 0,
            "oldest_article": oldest,
            "newest_article": newest,
            "total_feeds": len(RSS_FEEDS),
            "by_category": [{"cat": r[0] or "Општо", "n": r[1]} for r in by_cat],
            "by_source": [{"source": r[0], "n": r[1]} for r in by_source],
            "top_clicked": [{"title": r[0][:70], "source": r[1], "clicks": r[2], "link": r[3]} for r in top_clicks],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/favicon.ico")
def favicon():
    """Serve a simple SVG favicon — no file needed."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
      <rect width="32" height="32" fill="#8b1a1a"/>
      <text x="16" y="23" font-family="serif" font-size="20" font-weight="bold"
            text-anchor="middle" fill="#f2ead8">П</text>
    </svg>"""
    from flask import Response
    return Response(svg, mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.route("/cluster/<cluster_id>")
def cluster_page(cluster_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at DESC",
        (cluster_id,)
    ).fetchall()
    conn.close()
    if not rows:
        return "Кластерот не постои.", 404
    articles = [dict(r) for r in rows]
    articles = rank_articles_in_cluster(articles)
    return render_template("cluster.html",
        cluster_id=cluster_id,
        articles=articles,
        year=__import__('datetime').datetime.now().year
    )


@app.route("/proxy")
def image_proxy():
    """Proxy remote images to bypass hotlink 403s."""
    import urllib.request as _ur
    url = request.args.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return "", 400
    try:
        req = _ur.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Presek/1.0)",
            "Referer":    "",   # strip Referer to bypass hotlink protection
        })
        with _ur.urlopen(req, timeout=8) as resp:
            data        = resp.read()
            ctype       = resp.headers.get("Content-Type", "image/jpeg")
        from flask import Response as _R
        r = _R(data, mimetype=ctype)
        r.headers["Cache-Control"] = "public, max-age=3600"
        r.headers["X-Content-Type-Options"] = "nosniff"
        return r
    except Exception as e:
        log.warning(f"Image proxy failed for {url[:80]}: {e}")
        return "", 404


@app.route("/api/top10")
def api_top10():
    """Top 10 highest-scored clusters from the last 24 hours."""
    cached = cached_response("top10", ttl=60)
    if cached:
        return jsonify(cached)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    conn.close()
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    top = sorted(ranked, key=score_cluster, reverse=True)[:10]
    result = []
    for i, arts in enumerate(top):
        s   = score_cluster(arts)
        cid = arts[0]["cluster_id"] if arts else None
        result.append({
            "rank":          i + 1,
            "articles":      arts,
            "score":         round(s, 3),
            "cluster_id":    cid,
            "is_breaking":   s >= BREAKING_SCORE_THRESHOLD,
            "has_summary":   any(a.get("summary") for a in arts),
            "has_synthesis": cid in _cluster_summary_cache,
        })
    set_cache("top10", result)
    return jsonify(result)

@app.route("/arhiva")
def archive_page():
    return render_template("archive.html", year=__import__('datetime').datetime.now().year)

@app.route("/about")
def about_page():
    return render_template("about.html", year=__import__('datetime').datetime.now().year)

@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html", year=__import__('datetime').datetime.now().year)

@app.route("/contact")
def contact_page():
    return render_template("contact.html", year=__import__('datetime').datetime.now().year)

@app.route("/robots.txt")
def robots_txt():
    from flask import Response
    content = """User-agent: *
Allow: /
Disallow: /api/
Disallow: /proxy

Sitemap: https://presek.live/sitemap.xml
"""
    return Response(content, mimetype="text/plain")

@app.route("/sitemap.xml")
def sitemap_xml():
    from flask import Response
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    urls = [
        ("https://presek.live/", now, "always", "1.0"),
        ("https://presek.live/izvori", now, "monthly", "0.5"),
        ("https://presek.live/stats", now, "daily", "0.4"),
        ("https://presek.live/arhiva", now, "daily", "0.6"),
        ("https://presek.live/about", now, "monthly", "0.3"),
        ("https://presek.live/privacy", now, "monthly", "0.2"),
        ("https://presek.live/contact", now, "monthly", "0.2"),
    ]
    # Add recent cluster pages
    try:
        conn = get_db()
        clusters = conn.execute(
            "SELECT DISTINCT cluster_id, MAX(created_at) as latest FROM articles WHERE created_at >= datetime('now', '-7 days') GROUP BY cluster_id ORDER BY latest DESC LIMIT 100"
        ).fetchall()
        conn.close()
        for c in clusters:
            urls.append((f"https://presek.live/cluster/{c['cluster_id']}", c['latest'][:10], "daily", "0.7"))
    except Exception:
        pass

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod, freq, priority in urls:
        xml += f'  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq><priority>{priority}</priority></url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")

@app.route("/og-image.svg")
def og_image():
    """Generate a dynamic Open Graph image as SVG."""
    from flask import Response
    conn = get_db()
    count = conn.execute("SELECT COUNT(DISTINCT source) FROM articles WHERE created_at >= datetime('now', '-1 day')").fetchone()[0]
    conn.close()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
      <rect width="1200" height="630" fill="#151310"/>
      <rect x="0" y="0" width="1200" height="6" fill="#c04040"/>
      <text x="600" y="260" font-family="Georgia,serif" font-size="96" font-weight="bold" text-anchor="middle" fill="#c9a030">ПРЕСЕК</text>
      <text x="600" y="340" font-family="sans-serif" font-size="32" text-anchor="middle" fill="#d4c8a8">Македонски агрегатор на вести</text>
      <text x="600" y="420" font-family="sans-serif" font-size="24" text-anchor="middle" fill="#8a7c62">{count}+ извори · AI резимеа · Ажурирано на 15 мин</text>
      <rect x="0" y="624" width="1200" height="6" fill="#c04040"/>
    </svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})


@app.route("/api/archive")
def api_archive():
    """Return articles for a specific date, paginated."""
    date_str = request.args.get("date", "")
    page = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    page_size = min(page_size, 100)

    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        conn = get_db()
        # Count total for the day
        total = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE date(created_at) = ?",
            (date_str,)
        ).fetchone()[0]

        # Unique sources and categories for stats
        sources = conn.execute(
            "SELECT COUNT(DISTINCT source) FROM articles WHERE date(created_at) = ?",
            (date_str,)
        ).fetchone()[0]
        categories = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM articles WHERE date(created_at) = ?",
            (date_str,)
        ).fetchone()[0]

        # Paginated articles
        offset = page * page_size
        rows = conn.execute(
            "SELECT * FROM articles WHERE date(created_at) = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (date_str, page_size, offset)
        ).fetchall()
        conn.close()

        articles = [dict(r) for r in rows]
        return jsonify({
            "date": date_str,
            "total": total,
            "sources": sources,
            "categories": categories,
            "page": page,
            "page_size": page_size,
            "articles": articles,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return render_template("index.html", year=__import__('datetime').datetime.now().year)

if __name__ == "__main__":
    conn = get_db()
    # Create table if new install
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, link TEXT UNIQUE, source TEXT,
        category TEXT, summary TEXT, cluster_id TEXT,
        created_at TEXT, image_url TEXT
    )""")
    # Migrate existing DB — add image_url if not present
    cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if "image_url" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT DEFAULT ''")
        log.info("DB migrated: added image_url column")
    if "clicks" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN clicks INTEGER DEFAULT 0")
        log.info("DB migrated: added clicks column")
    if "description" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN description TEXT DEFAULT ''")
        log.info("DB migrated: added description column")
    if "subcategory" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN subcategory TEXT DEFAULT ''")
        log.info("DB migrated: added subcategory column")
    if "country" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN country TEXT DEFAULT '🇲🇰'")
        log.info("DB migrated: added country column")
    if "original_title" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN original_title TEXT DEFAULT ''")
        log.info("DB migrated: added original_title column")
    conn.commit()
    conn.close()

    threading.Thread(target=ingest_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
