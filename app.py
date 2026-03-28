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


def normalize_headline(title: str) -> str:
    """
    Convert ALL-CAPS headlines to Title Case, leaving normally-cased text untouched.

    Strategy: if >75% of the alphabetic characters in the title are uppercase,
    assume the source published in ALL CAPS and apply str.title(), which correctly
    capitalises proper nouns (Trump, Liverpool, Македонија) while not touching
    headlines that are already in mixed case.
    """
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
    """
    Remove common RSS 'signature' footers like 'The post ... appeared first on ...'
    which clutter the description and confuse the translation AI.
    """
    if not text:
        return ""
    import re as _re
    # 1. WordPress style: The post [Title] appeared first on [Site].
    text = _re.sub(r'The post\s+.*?\s+appeared first on\s+.*?(\.|$)', '', text, flags=_re.IGNORECASE | _re.DOTALL)
    # 2. Variant: This article was originally published on ...
    text = _re.sub(r'This article was originally published on\s+.*?(\.|$)', '', text, flags=_re.IGNORECASE | _re.DOTALL)
    # 3. Simple 'Source: [URL]' or 'Source: [Name]'
    text = _re.sub(r'Source:\s+https?://\S+', '', text, flags=_re.IGNORECASE)
    text = _re.sub(r'Source:\s+[A-Za-z0-9 ]+(\.|$)', '', text, flags=_re.IGNORECASE)
    # 4. "Read more at..."
    text = _re.sub(r'Read more at\s+.*?(\.|$)', '', text, flags=_re.IGNORECASE | _re.DOTALL)

    return text.strip()


def clean_json_response(text: str) -> str:
    """
    Robustly extract the summary text from a Gemini/AI response.
    Handles raw text, Markdown-wrapped JSON, and JSON objects.
    """
    if not text:
        return ""
    
    # 1. Strip markdown code blocks if they exist
    text = _re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    
    # 2. Try to find the bounds of a JSON object if it looks like one
    start_brace = text.find('{')
    end_brace = text.rfind('}')
    
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        json_part = text[start_brace:end_brace+1]
        try:
            import json
            data = json.loads(json_part)
            # If it's a dict with a 'summary' key, return just that
            if isinstance(data, dict) and 'summary' in data:
                return data['summary'].strip()
            # If it's just a dict/list, we'll fall through or return it as string
        except:
            pass # Not valid JSON, fall back to cleaned text

    return text.strip()


app = Flask(__name__)
CORS(app)
from flask_compress import Compress
Compress(app)

@app.before_request
def rate_limit_check():
    # Skip rate limiting for static files and the main page
    if request.path in ('/', '/favicon.ico') or request.path.startswith('/static'):
        return None
    # Behind a proxy like Cloudflare or Nginx, use X-Forwarded-For
    if request.headers.get("X-Forwarded-For"):
        ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
    else:
        ip = request.remote_addr or '0.0.0.0'
    if not check_rate_limit(ip):
        return jsonify({"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}), 429

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

REFRESH_INTERVAL = 300
FEED_LIMIT = 10
CLUSTER_LOOKBACK = 500  # increased from 200 — handles 36 sources × 10 entries per refresh

# Feed ETag / Last-Modified cache — avoids re-downloading unchanged feeds
_feed_etags:    dict[str, str] = {}
_feed_modified: dict[str, str] = {}

# Cluster-wide AI summaries — persisted to disk so they survive restarts
_cluster_summary_cache: dict[str, str] = {}
_SUMMARY_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cluster_summaries.json")

# On-demand deep analysis cache (in-memory only, resets on restart)
_analysis_cache: dict[str, str] = {}

def _load_summary_cache():
    global _cluster_summary_cache
    try:
        if os.path.exists(_SUMMARY_CACHE_PATH):
            with open(_SUMMARY_CACHE_PATH, "r", encoding="utf-8") as f:
                _cluster_summary_cache = json.load(f)
            log.info(f"Loaded {len(_cluster_summary_cache)} cached cluster summaries.")
    except Exception as e:
        log.warning(f"Could not load summary cache: {e}")

def _save_summary_cache():
    try:
        with open(_SUMMARY_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cluster_summary_cache, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f"Could not save summary cache: {e}")

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
    # ── Batch 6 — Sourced from time.mk ───────────────────────────
    ("IRL",             "https://irl.mk/mk/feed/"),
    ("Nova TV",         "https://novatv.mk/feed/"),
    ("Libertas",        "https://libertas.mk/feed/"),
    ("Racin",           "https://racin.mk/feed/"),
    ("Kajgana",         "https://kajgana.com/rss.xml"),
    ("Pari.com.mk",     "https://pari.com.mk/feed/"),
    ("Bloomberg Adria", "https://mk.bloombergadria.com/rss"),
    ("E-Magazin",       "https://emagazin.mk/feed/"),
    ("IT.mk",           "https://it.mk/feed/"),
    ("Sportmanija",     "https://sportmanija.mk/feed/"),
    ("Fakulteti",       "https://fakulteti.mk/rss"),
    ("Magazin",         "https://magazin.mk/feed/"),
]

# Feeds that publish only one type of content — no need to run keyword detection.
# Category is applied at ingest time, skipping detect_category() for these sources.
HARDCODED_FEED_CATEGORIES: dict[str, str] = {
    # No hardcoded domestic category overrides — keyword detection handles all MK sources.
}

# Sources that publish in Macedonian — no Gemini translation needed.
# Used in ingest_diaspora_feeds() to skip unnecessary API calls if any of these
# ever appear in DIASPORA_FEEDS, and as a guard against accidental translation.
MK_LANGUAGE_SOURCES: frozenset[str] = frozenset({
    "Sloboden Pecat", "Kanal 5", "MIA", "Sitel", "Telma", "Kurir",
    "Republika", "Fokus", "Nezavisen", "Faktor", "Vecer", "Meta",
    "360 Stepeni", "Makfax", "Nova Makedonija", "Infomax", "Press24",
    "Skopje1", "Plusinfo", "Lokalno", "4News", "Makpress", "Vistinomer",
    "Portalb", "Lider", "MKD", "NetPress", "Akademik", "Skopje Info",
    "Prizma", "Expres", "Tetovo Info", "Koha", "A1on", "SportSport",
    "Strumica Info", "24 Вести", "TV21", "Слободна Европа",
    "Deutsche Welle", "Журнал", "Civil Media", "Радио МОФ",
    "Сакам да кажам", "Бизнис Вести", "Ohrid News", "Vecer Sport",
    "Ekonomija", "Zdravje", "MRT", "Time.mk", "Kolumna", "Okno",
    "Alfa TV", "Tocka", "IRL", "Nova TV", "Libertas", "Racin",
    "Kajgana", "Pari.com.mk", "Bloomberg Adria", "E-Magazin",
    "IT.mk", "Sportmanija", "Fakulteti", "Magazin",
})

DIASPORA_FEEDS = [
    # 🇩🇪 Germany
    ("Tagesschau",          "https://www.tagesschau.de/xml/rss2",                               "Германија"),
    ("Der Spiegel",         "https://www.spiegel.de/schlagzeilen/index.rss",                    "Германија"),
    ("Deutsche Welle DE",   "https://rss.dw.com/rdf/rss-de-all",                               "Германија"),
    ("Deutsche Welle EN",   "https://rss.dw.com/rdf/rss-en-ger",                               "Германија"),
    ("ZDF Heute",           "https://www.zdf.de/rss/zdf/nachrichten",                          "Германија"),
    ("Süddeutsche Zeitung", "https://rss.sueddeutsche.de/rss/Topthemen",                       "Германија"),
    ("Die Zeit",            "https://newsfeed.zeit.de/index",                                   "Германија"),
    # 🇨🇭 Switzerland
    ("SRF News",    "https://www.srf.ch/news/bnf/rss/1890",                                     "Европа"),
    ("20 Minuten",  "https://www.20min.ch/rss/rss.tmpl?type=channel&get=4",                     "Европа"),
    # 🇺🇸 USA
    ("CNN",         "http://rss.cnn.com/rss/cnn_topstories.rss",                                 "Америка"),
    ("NPR",         "https://feeds.npr.org/1001/rss.xml",                                        "Америка"),
    ("Reuters",     "https://www.reutersagency.com/feed/",                                       "Свет"),
    # 🇨🇦 Canada
    ("CBC News",        "https://rss.cbc.ca/lineup/topstories.xml",                             "Америка"),
    ("Fox News Latest", "https://moxie.foxnews.com/google-publisher/latest.xml",                "Америка"),
    ("Fox News World",  "https://moxie.foxnews.com/google-publisher/world.xml",                 "Америка"),
    ("BBC US/Canada",   "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",            "Америка"),
    # 🇬🇧 United Kingdom
    ("BBC News",        "https://feeds.bbci.co.uk/news/rss.xml",                                "Европа"),
    ("The Guardian",    "https://www.theguardian.com/world/rss",                                "Европа"),
    ("France24",        "https://www.france24.com/en/europe/rss",                               "Европа"),
    ("EuroNews",        "https://feeds.feedburner.com/euronews/en/home/",                       "Европа"),
    ("Politico Europe", "https://www.politico.eu/feed",                                         "Европа"),
    # 🇦🇺 Australia
    ("ABC Australia",   "https://www.abc.net.au/news/feed/2942460/rss.xml",                     "Свет"),
    ("Al Jazeera",      "https://www.aljazeera.com/xml/rss/all.xml",                            "Свет"),
    ("SCMP",            "https://www.scmp.com/rss/91/feed",                                     "Свет"),
    ("NHK World",       "https://www3.nhk.or.jp/rss/news/cat0.xml",                             "Свет"),
    ("Times of India",  "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",           "Свет"),
    ("RFI English",     "https://www.rfi.fr/en/rss",                                            "Свет"),
    # 🇮🇹 Italy
    ("ANSA",        "https://www.ansa.it/sito/ansait_rss.xml",                                   "Европа"),
    # 🇸🇮 Slovenia
    ("RTVSLO",      "https://www.rtvslo.si/feeds/00.xml",                                       "Словенија"),
    # 🇦🇹 Austria
    ("ORF",         "https://rss.orf.at/news.xml",                                               "Австрија"),
    # 🇸🇪 Sweden
    ("SVT News",    "https://www.svt.se/nyheter/rss.xml",                                        "Шведска"),
    # 🇷🇸 Serbia / Balkans
    ("N1 Info",     "https://n1info.rs/feed/",                                                   "Балкан"),
    ("B92",         "https://www.b92.net/info/rss/vesti.xml",                                    "Балкан"),
    # 🇷🇸 Serbia — high readership in Macedonia
    ("Kurir.rs",     "https://www.kurir.rs/rss",                                                 "Балкан"),
    ("Blic.rs",      "https://www.blic.rs/rss",                                                  "Балкан"),
    # 🇧🇬 Bulgaria
    ("Novinite",    "https://www.novinite.com/rss.php",                                          "Балкан"),
    # 🇬🇷 Greece
    ("Kathimerini", "https://www.ekathimerini.com/rss",                                          "Балкан"),
    # 🇦🇱 Albania / Kosovo
    ("Exit News",   "https://exit.al/en/feed/",                                                  "Балкан"),
    ("Top Channel", "https://top-channel.tv/feed/",                                              "Албанија"),
    # 🇽🇰 Kosovo
    ("Telegrafi",    "https://telegrafi.com/feed/",                                              "Балкан"),
    # 🇹🇷 Turkey (included in Балкан per site taxonomy)
    ("Daily Sabah",  "https://www.dailysabah.com/rssFeed/politics",                              "Балкан"),
    ("TRT World",    "https://www.trtworld.com/content/rss.xml",                                 "Балкан"),
    # 🌍 Balkans investigative
    ("Balkan Insight", "https://balkaninsight.com/feed/",                                        "Балкан"),
    # 🇭🇷 Croatia
    ("Index.hr",     "https://index.hr/rss",                                                     "Балкан"),
    ("Jutarnji",     "https://www.jutarnji.hr/feed",                                             "Балкан"),
    # 🇧🇦 Bosnia
    ("Klix.ba",      "https://www.klix.ba/rss",                                                  "Балкан"),
    # 🇲🇪 Montenegro
    ("Vijesti.me",   "https://www.vijesti.me/rss",                                               "Балкан"),
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
    "RTVSLO":           1.7,  # Slovenian public broadcaster
    "ORF":              1.7,  # Austrian public broadcaster
    "SVT News":         1.7,  # Swedish public broadcaster
    "Top Channel":      1.6,  # Albanian major TV
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
    "Index.hr":         1.5,
    "Jutarnji":         1.4,
    "Klix.ba":          1.4,
    "Vijesti.me":       1.3,
    "IRL":              1.8,
    "Nova TV":          1.3,
    "Libertas":         1.1,
    "Racin":            1.3,
    "Kajgana":          1.0,
    "Pari.com.mk":      1.2,
    "Bloomberg Adria":  1.4,
    "E-Magazin":        1.1,
    "IT.mk":            1.1,
    "Sportmanija":      0.8,
    "Fakulteti":        1.1,
    "Magazin":          0.8,
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
        feed = feedparser.parse(
            url,
            etag=_feed_etags.get(url),
            modified=_feed_modified.get(url),
            request_headers={"User-Agent": "Presek.mk/1.0"},
        )
        # 304 Not Modified — nothing new
        if getattr(feed, "status", 200) == 304:
            return source, [], None
        # Store ETag / Last-Modified for next poll
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
    try:
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
                forced     = HARDCODED_FEED_CATEGORIES.get(source)
                category   = detect_category(title, description=desc, source=source, forced_category=forced)
                subcategory = detect_subcategory(title, description=desc) or ""
                cluster_id = clustering.find_or_create_cluster(title, recent_articles)
                now        = datetime.datetime.now().isoformat()
                # Strip HTML tags and remove common footers for clean storage
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


def translate_titles_batch(titles: list[str]) -> list[str]:
    """Translate a list of texts to Macedonian using numbered-line batches."""
    if not titles or not GOOGLE_API_KEY:
        return [None] * len(titles)

    BATCH_SIZE = 5
    result: list[str | None] = list(titles)  # start with originals as fallback
    
    # Define a stricter system prompt to avoid concatenation issues
    SYSTEM_PROMPT = (
        "You are a professional translator to Macedonian. "
        "Translate the input texts accurately. "
        "Return ONLY the Macedonian translation. "
        "DO NOT include the original text, DO NOT include labels like 'Translation:', "
        "and DO NOT include any extra notes or explanations."
    )

    for start in range(0, len(titles), BATCH_SIZE):
        batch = titles[start:start + BATCH_SIZE]
        prompt = (
            f"Translate these {len(batch)} news texts to Macedonian. "
            "Return ONLY a raw JSON array of strings in the exact same order. "
            f"Format: [\"Text 1\", ..., \"Text {len(batch)}\"]\n\n"
            + json.dumps(batch, ensure_ascii=False)
        )
        translations = None
        for attempt in range(3):  # retry twice
            time.sleep(10)  # Long rate limit protection
            raw = _call_gemini(prompt, SYSTEM_PROMPT + " Respond with JSON array only.", timeout=45, max_tokens=2000, json_mode=True)
            if not raw:
                continue
            
            # Sanitize output using our robust cleaner
            response_text = clean_json_response(raw)
            
            try:
                data = json.loads(response_text)
                if isinstance(data, list) and len(data) == len(batch):
                    translations = data
                    break
                else:
                    log.warning(f"[diaspora] JSON mismatch at {start}: expected {len(batch)}, got {len(data) if isinstance(data, list) else 'non-list'}. Raw length: {len(raw)}")
            except Exception as e:
                log.warning(f"[diaspora] JSON parse error at {start}: {e}. Raw length: {len(raw)}")
                log.error(f"Failed response text: {raw}")
            
            time.sleep(1)

        if translations:
            for j, t in enumerate(translations):
                result[start + j] = t
        else:
            log.warning(f"[diaspora] Batch translation failed at {start}, falling back to single items...")
            for j, title in enumerate(batch):
                time.sleep(2)
                single_prompt = f"Translate this text to Macedonian. Return ONLY the translated string, no JSON, no quotes unless part of text.\n\nText: {title}"
                res = _call_gemini(single_prompt, SYSTEM_PROMPT, max_tokens=400)
                if res:
                    result[start + j] = res
                else:
                    log.warning(f"[diaspora] Single translation failed for item {start+j}")

    return result


def ingest_diaspora_feeds():
    """Fetch diaspora RSS feeds and write to DB separately (without translation)."""
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

    import re as _re

    # Phase 2: write to DB sequentially
    conn = get_db()
    try:
        new_count = 0
        for i, (source, title, link, desc, image_url, category, country) in enumerate(all_entries):
            try:
                if conn.execute("SELECT id FROM articles WHERE link = ?", (link,)).fetchone():
                    continue
                
                # All Diaspora feeds now SKIP translation. 
                # Store 'original_title' as the main 'title' in the database.
                display_title = normalize_headline(title)
                cluster_id = clustering.find_or_create_cluster(display_title, diaspora_recent)
                now = datetime.datetime.now().isoformat()
                
                # Strip HTML tags and remove common footers for clean storage
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


def _call_gemini(prompt_text: str, system_prompt: str, timeout: int = 25, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    """Shared Gemini caller. Retries with exponential backoff on rate-limit (429)."""
    if not GOOGLE_API_KEY:
        return None
    prompt_text = prompt_text[:10000]
    
    gen_config = {"maxOutputTokens": max_tokens}
    if json_mode:
        gen_config["responseMimeType"] = "application/json"
        
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": gen_config
    }).encode("utf-8")
    # Financial Safety Rail: Mandatory 1s delay between any two global API calls
    time.sleep(1)
    
    delays = [2, 4, 8]  # seconds before each retry (3 attempts total)
    for attempt, delay in enumerate([0] + delays):
        if delay:
            time.sleep(delay)
        try:
            req = urllib.request.Request(
                f"{GEMINI_URL}?key={GOOGLE_API_KEY}",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning(f"[gemini] Rate limited (429), retry {attempt+1}/3 in {delays[attempt] if attempt < len(delays) else '—'}s")
                continue
            log.warning(f"[gemini] HTTP {e.code}: {e}")
            return None
        except Exception as e:
            import traceback as _tb
            log.warning(f"[gemini] Call failed: {e}\n" + _tb.format_exc())
            return None
    log.warning("[gemini] All retries exhausted after rate limiting.")
    return None


def _call_ai(prompt_text: str, system_prompt: str, max_tokens: int = 2000, json_mode: bool = False) -> tuple[str | None, str | None]:
    """Call Gemini API. Returns (summary, 'gemini') or (None, None)."""
    result = _call_gemini(prompt_text, system_prompt, max_tokens=max_tokens, json_mode=json_mode)
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
                time.sleep(6)  # enforce strict 6s delay for rate limit

        # 2. Generate cluster synthesis (if multi-source and not cached)
        unique_sources = {a["source"] for a in arts}
        if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC and cid not in _cluster_summary_cache:
            headlines = "\n".join(
                f"- [{a['source']}]: {a['title']}"
                for a in arts[:10]
            )
            synthesis, tier = _call_ai(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True)
            if synthesis:
                clean_synthesis = clean_json_response(synthesis)
                _cluster_summary_cache[cid] = clean_synthesis
                synthesis_count += 1
                time.sleep(6)  # enforce strict 6s delay for rate limit

    if summarized_count or synthesis_count:
        log.info(f"[auto-summarize] {summarized_count} article summaries, {synthesis_count} cluster syntheses generated.")
        _save_summary_cache()

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
        log.info(f"Ingest loop sleeping for {REFRESH_INTERVAL}s...")
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
    country   = request.args.get("country", "🇲🇰")
    page_size = min(page_size, 100)  # cap at 100
    cache_key = f"news:{country}:{page}:{page_size}"
    cached = cached_response(cache_key, ttl=30)
    if cached:
        return jsonify(cached)
    # Fetch articles filtered by country, then cluster them
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE country = ? ORDER BY created_at DESC LIMIT 500",
        (country,)
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
    return jsonify(result[:10])


SUMMARY_SYSTEM_PROMPT = (
    "Ти си професионален уредник на македонска новинска агенција. "
    "Даден ти е наслов на вест на македонски јазик. "
    "Одговори ИСКЛУЧИВО на стандарден литературен македонски јазик. НЕ користи српски, хрватски или бугарски зборови. "
    "Правопис: Секогаш правилно пишувај ги сопствените именки (имиња на луѓе, градови, држави, организации) — "
    "без разлика дали во изворот се напишани со голема или мала буква. "
    "На пример: Трамп, Иран, Скопје, НАТО, ЕУ, Владата — НИКОГАШ сите мали. "
    "САМО во овој формат без никаков додатен текст:\n"
    "Ред 1: Сентимент — точно еден емоџи: 🟢 (позитивно) или 🔴 (негативно) или ⚪ (неутрално)\n"
    "Ред 2-3: ТОЧНО ДВЕ (2) кратки, фактички реченици кои го објаснуваат контекстот. Не повеќе, не помалку. Отстрани секаков сензационализам и кликбејт.\n"
    "Ред 4: Три до пет клучни зборови со # (пример: #Скопје #Влада #Буџет)\n"
    "Важно: Не пишувај воведни фрази, наслови, или објаснувања. Само форматот."
)

SYNTHESIS_SYSTEM_PROMPT = (
    "Ти си искусен уредник на македонска новинска агенција. "
    "Дадени ти се наслови за иста вест од различни медиуми. "
    "Write a comprehensive, detailed synthesis consisting of at least 3 to 4 full paragraphs. "
    "You must write the entire response strictly in the Macedonian language. "
    "Return ONLY a valid JSON object in the format: {\"summary\": \"...\"}. "
    "Do NOT wrap the response in ```json or any other markdown formatting. "
    "Start directly with { and end with }. "
    "Do NOT use literal quotation marks inside the summary text. Use single quotes (') or escape double quotes (\\\") to ensure the JSON does not break. "
    "Do NOT use bullet points or complex markdown. "
    "Секогаш правилно пишувај ги сопствените именки (имиња на луѓе, градови, држави, организации) — "
    "без разлика дали во изворите се напишани со голема или мала буква. "
    "На пример: Трамп, Иран, Скопје, НАТО, ЕУ, Владата — НИКОГАШ сите мали."
)

ANALYSIS_SYSTEM_PROMPT = (
    "Ти си аналитичар на македонска новинска агенција. "
    "Дадени ти се наслови и описи на новински статии за иста приказна. "
    "Одговори ИСКЛУЧИВО на стандарден литературен македонски јазик. "
    "НЕ користи српски, хрватски или бугарски зборови. "
    "Дај структурирана анализа во ТОЧНО овој формат без никаков додатен текст:\n"
    "🔑 Клучни факти:\n• [факт 1]\n• [факт 2]\n• [факт 3 ако постои]\n"
    "📊 Бројки и статистики: [конкретни бројки ако ги има, или 'Нема конкретни бројки во изворите']\n"
    "✅ Потврдени информации: [само потврдено, без шпекулации]\n"
    "💡 Кратка анализа: [точно две реченици за контекстот и значењето на настанот]\n"
    "Важно: Биди конкретен и факти-базиран. Не шпекулирај. Само форматот."
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

    summary = clean_json_response(summary)
    
    conn.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    conn.commit()
    conn.close()
    return jsonify({"summary": summary, "cached": False, "tier": tier})


@app.route("/api/cluster-summary/<cluster_id>")
def api_cluster_summary(cluster_id: str):
    """
    Cluster-wide AI synthesis — feeds all articles in a cluster to Gemini
    and returns a cross-source summary with multiple perspectives.
    Results are cached in memory and in the cluster_summaries database table.
    """
    if cluster_id in _cluster_summary_cache:
        return jsonify({"summary": _cluster_summary_cache[cluster_id], "cached": True})

    conn = get_db()
    try:
        # 1. DB cache check
        row = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = ?", (cluster_id,)).fetchone()
        if row:
            summary = row["summary"]
            _cluster_summary_cache[cluster_id] = summary
            # We still need source count for the response, so fetch relevant articles
            count_row = conn.execute("SELECT COUNT(*) as count FROM articles WHERE cluster_id = ?", (cluster_id,)).fetchone()
            return jsonify({
                "summary": summary,
                "source_count": count_row["count"] if count_row else 0,
                "cached": True,
                "tier": "db_cache"
            })

        # 2. Fetch articles for synthesis if not in cache
        rows = conn.execute(
            "SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at ASC LIMIT 10",
            (cluster_id,)
        ).fetchall()

        if not rows:
            return jsonify({"error": "Cluster not found"}), 404

        articles = [dict(r) for r in rows]
        headlines = "\n".join(f"- [{a['source']}]: {a['title']}" for a in articles)

        # 3. Call Gemini with error handling for 429s
        try:
            raw_res = _call_gemini(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True)
            if not raw_res:
                return jsonify({"error": "AI сервисот е недостапен."}), 503
            
            # --- Cleanup logic to sanitize Gemini response ---
            summary = clean_json_response(raw_res)
            
            # 4. Success: Save to DB and memory cache
            now = datetime.datetime.now().isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO cluster_summaries (cluster_id, summary, created_at) VALUES (?, ?, ?)",
                (cluster_id, summary, now)
            )
            conn.commit()
            _cluster_summary_cache[cluster_id] = summary
            
            return jsonify({"summary": summary})
            
        except Exception as e:
            if '429' in str(e) or 'ResourceExhausted' in str(e):
                return jsonify({"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."})
            return jsonify({"error": "AI сервисот е недостапен."}), 503
            
    finally:
        conn.close()


@app.route("/api/analyze/<cluster_id>")
def api_analyze(cluster_id: str):
    """
    On-demand deep analysis of a cluster — key facts, numbers/statistics,
    confirmed information, and a brief situational analysis.
    Results are cached in memory for the lifetime of the process.
    """
    import traceback as _tb

    if cluster_id in _analysis_cache:
        return jsonify({"analysis": _analysis_cache[cluster_id], "cached": True})

    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at ASC LIMIT 10",
            (cluster_id,)
        ).fetchall()
        conn.close()
    except Exception:
        log.error("[analyze] DB error:\n" + _tb.format_exc())
        return jsonify({"error": "Database error"}), 500

    if not rows:
        log.warning(f"[analyze] No articles found for cluster_id={cluster_id!r}")
        return jsonify({"error": "Cluster not found"}), 404

    articles = [dict(r) for r in rows]

    # Build prompt content — titles are always present; descriptions are optional
    lines = []
    for a in articles:
        line = f"- [{a['source']}]: {a['title']}"
        desc = (a.get('description') or '').strip()
        if desc:
            # Strip HTML tags that may have slipped through
            import re as _re
            desc = _re.sub(r'<[^>]+>', '', desc)[:250].strip()
            line += f"\n  Опис: {desc}"
        lines.append(line)
    content = "\n".join(lines)

    if not content.strip():
        log.warning(f"[analyze] Empty content for cluster_id={cluster_id!r}")
        return jsonify({"error": "Нема доволно содржина за анализа."}), 422

    log.info(f"[analyze] Calling Gemini for cluster {cluster_id!r} ({len(articles)} articles)")
    log.debug(f"[analyze] Prompt content:\n{content}")

    try:
        # Call Gemini directly with a slightly longer timeout for richer prompts
        analysis = _call_gemini(
            f"Статии:\n{content}",
            ANALYSIS_SYSTEM_PROMPT,
            timeout=40,
        )
    except Exception:
        log.error("[analyze] Gemini call raised an exception:\n" + _tb.format_exc())
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    if not analysis:
        log.warning(f"[analyze] Gemini returned empty/None for cluster {cluster_id!r}")
        # Check whether the API key is configured at all
        if not GOOGLE_API_KEY:
            log.error("[analyze] GOOGLE_API_KEY is not set!")
            return jsonify({"error": "API клучот не е конфигуриран."}), 503
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    log.info(f"[analyze] Got analysis ({len(analysis)} chars) for cluster {cluster_id!r}")
    analysis = clean_json_response(analysis)
    _analysis_cache[cluster_id] = analysis
    return jsonify({"analysis": analysis, "cached": False})


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
    for arts in sorted_clusters[:10]:
        result.append({
            "articles":    arts,
            "score":       round(score_cluster(arts), 3),
            "cluster_id":  arts[0]["cluster_id"],
            "total_clicks": sum(a.get("clicks",0) for a in arts),
            "is_breaking": False,
        })
    set_cache("popular", result)
    return jsonify(result)


@app.route("/api/chat_cluster", methods=["POST"])
def api_chat_cluster():
    """Real-time conversation with a specific news cluster."""
    data = request.json
    cluster_id = data.get("cluster_id")
    query = data.get("query")
    if not cluster_id or not query:
        return jsonify({"error": "Missing cluster_id or query"}), 400

    conn = get_db()
    rows = conn.execute("SELECT source, title, description FROM articles WHERE cluster_id = ?", (cluster_id,)).fetchall()
    conn.close()
    if not rows:
        return jsonify({"error": "Cluster not found"}), 404

    # Construct a lean, token-efficient context (Source + Title + Truncated Snippet)
    context_items = []
    for r in rows:
        snippet = (r['description'] or "")[:120] + "..." if r['description'] else "No snippet"
        context_items.append(f"SOURCE: {r['source']}\nHEADLINE: {r['title']}\nSNIPPET: {snippet}")
    
    context_text = "\n---\n".join(context_items)
    
    system_instruction = """
Ти си Главен Аналитичар (Chief Analyst) за 'Пресек', премиум македонски агрегатор на вести.
Твојата задача е да им дадеш на корисниците објективен, јасен и прецизен преглед на вестите базиран на понудените извори.

Твоите новинарски правила:
1. НУЛТА ПРИСТРАСНОСТ: Мораш да останеш апсолутно неутрален. Не заземај страна во македонската или глобалната политика.
2. ФОКУС НА ИЗВОРИТЕ: Секогаш кога е можно, посочувај кој медиум што кажал (на пр. "Сител известува дека..., додека Слободен Печат додава...").
3. БЕЗ ПАНИКА: Известувај за трагедии, криминал или војна со ладна глава и почит. Избегнувај сензационализам.
4. КОНЦИЗНОСТ: Одговорите нека бидат кратки, структурирани со точки (bullet points) и лесни за скенирање. Избегнувај долги воведи.
5. КОНТЕКСТ: Ако корисникот праша за нешто што го нема во дадените наслови, користи го твоето пребарување (Search tool) за да дадеш точен, глобален или историски контекст, но јасно напомени дека е дополнителна информација.
6. РЕЛЕВАНТНОСТ: Фокусирај се на факти и сериозна анализа. Игнорирај шпекулации или озборувања кои не се поткрепени со изворите.
"""

    user_prompt = f"""
CLUSTER CONTEXT (Macedonian Media):
{context_text}

USER QUESTION:
{query}
"""

    # Refined Grounding Triggers
    grounding_keywords = [
        "зошто", "свет", "историја", "анализа", "влијание", "последици", 
        "минатото", "контекст", "кога", "очекува", "иднина", "сад", "еу", "русија"
    ]
    needs_grounding = any(word in query.lower() for word in grounding_keywords)

    try:
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "tools": [{"google_search_retrieval": {}}] if needs_grounding else []
        }
        
        req = urllib.request.Request(f"{GEMINI_URL}?key={GOOGLE_API_KEY}",
                          data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req, timeout=25) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data["candidates"][0]["content"]["parts"][0]["text"]
            
            return jsonify({
                "response": answer,
                "grounded": needs_grounding
            })
    except Exception as e:
        log.error(f"AI Chat error: {e}")
        return jsonify({"error": "AI сервисот е моментално преоптоварен."}), 503


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
        sorted_c = sorted(ranked, key=score_cluster, reverse=True)[:10]
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
            "by_category": [{"cat": r[0] or "Македонија", "n": r[1]} for r in by_cat],
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
    
    # Get synthesis summary if available
    synthesis = _cluster_summary_cache.get(cluster_id)
    
    return render_template("cluster.html",
        cluster_id=cluster_id,
        articles=articles,
        synthesis=synthesis,
        year=__import__('datetime').datetime.now().year
    )


@app.route("/proxy")
def image_proxy():
    """Proxy remote images to bypass hotlink 403s."""
    import urllib.request as _ur
    from urllib.parse import urlparse as _urlparse, urlunparse as _urlunparse, quote as _quote
    url = request.args.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return "", 400
    try:
        # Percent-encode non-ASCII characters in path/query (fixes Cyrillic URLs)
        _p = _urlparse(url)
        safe_url = _urlunparse(_p._replace(
            path=_quote(_p.path, safe='/:@!$&\'()*+,;='),
            query=_quote(_p.query, safe='=&+%'),
        ))
        req = _ur.Request(safe_url, headers={
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
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Base static URLs
    urls = [
        ("https://presek.live/", now, "always", "1.0"),
        ("https://presek.live/izvori", now, "monthly", "0.5"),
        ("https://presek.live/stats", now, "daily", "0.4"),
        ("https://presek.live/arhiva", now, "daily", "0.6"),
        ("https://presek.live/about", now, "monthly", "0.3"),
        ("https://presek.live/privacy", now, "monthly", "0.2"),
        ("https://presek.live/contact", now, "monthly", "0.2"),
    ]
    
    # Add dynamic cluster pages from the last 14 days (DB_RETAIN_DAYS)
    try:
        conn = get_db()
        clusters = conn.execute(
            "SELECT cluster_id, MAX(created_at) as latest "
            "FROM articles "
            "WHERE created_at >= datetime('now', '-14 days') "
            "GROUP BY cluster_id "
            "ORDER BY latest DESC"
        ).fetchall()
        conn.close()
        
        for c in clusters:
            # Extract YYYY-MM-DD from the timestamp
            lastmod = c['latest'][:10] if c['latest'] else now
            urls.append((f"https://presek.live/cluster/{c['cluster_id']}", lastmod, "daily", "0.7"))
    except Exception as e:
        log.error(f"Sitemap DB error: {e}")

    # Generate XML
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod, freq, priority in urls:
        xml += (
            f'  <url>\n'
            f'    <loc>{loc}</loc>\n'
            f'    <lastmod>{lastmod}</lastmod>\n'
            f'    <changefreq>{freq}</changefreq>\n'
            f'    <priority>{priority}</priority>\n'
            f'  </url>\n'
        )
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
      <text x="600" y="420" font-family="sans-serif" font-size="24" text-anchor="middle" fill="#8a7c62">{count}+ извори · AI резимеа · Ажурирано на 5 мин</text>
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
    # Create tables if new install
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, link TEXT UNIQUE, source TEXT,
        category TEXT, summary TEXT, cluster_id TEXT,
        created_at TEXT, image_url TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
        cluster_id TEXT PRIMARY KEY,
        summary TEXT,
        created_at TEXT
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
    # Add indexes for common query patterns
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON articles(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category_created ON articles(category, created_at DESC)")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    conn = get_db()
    # Create tables with reorganized schema if new install
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cluster_id TEXT NOT NULL,
        source TEXT NOT NULL,
        link TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        original_title TEXT DEFAULT '',
        description TEXT DEFAULT '',
        summary TEXT,
        category TEXT,
        subcategory TEXT DEFAULT '',
        country TEXT DEFAULT 'Македонија',
        created_at TEXT NOT NULL,
        image_url TEXT,
        clicks INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
        cluster_id TEXT PRIMARY KEY,
        summary TEXT,
        created_at TEXT
    )""")
    
    # Ensure indexes exist for performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_country_created ON articles(country, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category_created ON articles(category, created_at DESC)")
    conn.commit()
    conn.close()

    _load_summary_cache()
    threading.Thread(target=ingest_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

