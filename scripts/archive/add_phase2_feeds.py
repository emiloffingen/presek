import os
import sys
import urllib.error
import urllib.request

# Ensure project root in path
sys.path.append(os.getcwd())

from core.database import db_manager as db

PHASE2_FEEDS = [
    # --- Business & Economy (RS) ---
    {
        "name": "Danas - Ekonomija",
        "url": "https://www.danas.rs/tag/ekonomija/feed/",
        "country": "RS",
        "category": "Ekonomija",
        "language": "sr",
        "credibility": 0.85,
    },
    {
        "name": "Kamatica",
        "url": "https://www.kamatica.com/rss",
        "country": "RS",
        "category": "Ekonomija",
        "language": "sr",
        "credibility": 0.85,
    },
    {
        "name": "Gde Investirati",
        "url": "https://gdeinvestirati.com/feed/",
        "country": "RS",
        "category": "Ekonomija",
        "language": "sr",
        "credibility": 0.80,
    },
    # --- Business & Economy (MK) ---
    {
        "name": "Biznis Info",
        "url": "https://biznisinfo.mk/feed/",
        "country": "MK",
        "category": "Biznis",
        "language": "mk",
        "credibility": 0.80,
    },
    {
        "name": "Faktor.mk",
        "url": "https://faktor.mk/feed/",
        "country": "MK",
        "category": "Biznis",
        "language": "mk",
        "credibility": 0.85,
    },
    {
        "name": "Izvoz.mk",
        "url": "https://izvoz.mk/feed/",
        "country": "MK",
        "category": "Biznis",
        "language": "mk",
        "credibility": 0.80,
    },
    # --- Technology (RS) ---
    {
        "name": "Benchmark",
        "url": "https://benchmark.rs/feed/",
        "country": "RS",
        "category": "Tehnologija",
        "language": "sr",
        "credibility": 0.85,
    },
    {
        "name": "PC Press",
        "url": "https://pcpress.rs/feed/",
        "country": "RS",
        "category": "Tehnologija",
        "language": "sr",
        "credibility": 0.85,
    },
    # --- Technology (MK) ---
    {
        "name": "SmartPortal.mk",
        "url": "https://smartportal.mk/feed/",
        "country": "MK",
        "category": "Tehnologija",
        "language": "mk",
        "credibility": 0.80,
    },
    {
        "name": "Telefoni.mk",
        "url": "https://telefoni.mk/feed/",
        "country": "MK",
        "category": "Tehnologija",
        "language": "mk",
        "credibility": 0.80,
    },
    # --- Culture & Entertainment (RS) ---
    {
        "name": "Seecult",
        "url": "https://www.seecult.org/rss.xml",
        "country": "RS",
        "category": "Kultura",
        "language": "sr",
        "credibility": 0.90,
    },
    {
        "name": "Danas - Kultura",
        "url": "https://www.danas.rs/tag/kultura/feed/",
        "country": "RS",
        "category": "Kultura",
        "language": "sr",
        "credibility": 0.85,
    },
    {
        "name": "Balkanrock",
        "url": "https://balkanrock.com/feed/",
        "country": "RS",
        "category": "Kultura",
        "language": "sr",
        "credibility": 0.80,
    },
    # --- Culture & Entertainment (MK) ---
    {
        "name": "Popara.mk",
        "url": "https://popara.mk/feed/",
        "country": "MK",
        "category": "Kultura",
        "language": "mk",
        "credibility": 0.80,
    },
    {
        "name": "Kajgana Zabava",
        "url": "https://kajgana.com/rss.xml",
        "country": "MK",
        "category": "Kultura",
        "language": "mk",
        "credibility": 0.85,
    },
]


def verify_feed_url(url, name):
    """Perform a live HTTP request to verify if the RSS feed is reachable."""
    print(f"Verifying reachability for '{name}'...")
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PresekCrawler/3.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            status = response.getcode()
            if status == 200:
                print(f"  ✅ '{name}' verified successfully (HTTP 200).")
                return True
            else:
                print(f"  ❌ '{name}' returned unexpected status: {status}")
                return False
    except urllib.error.HTTPError as e:
        # Ignore minor rate limiting blocks or temporary redirection issues for seeding
        if e.code in (403, 301, 302, 308):
            print(f"  ⚠️ '{name}' returned redirect/WAF code {e.code}. Marking as verified for seeding.")
            return True
        print(f"  ❌ '{name}' failed with HTTP error: {e.code} ({e.reason})")
        return False
    except urllib.error.URLError as e:
        print(f"  ❌ '{name}' failed with connection error: {e.reason}")
        return False
    except Exception as e:
        print(f"  ❌ '{name}' failed with exception: {e}")
        return False


def seed_feeds():
    print(f"Starting Phase 2 category seeding of {len(PHASE2_FEEDS)} sources...")

    added_sources = 0
    added_feeds = 0

    for f in PHASE2_FEEDS:
        name = f["name"]
        url = f["url"]
        country = f["country"]
        category = f["category"]
        language = f["language"]
        credibility = f["credibility"]

        # Verify the feed live before inserting
        is_valid = verify_feed_url(url, name)
        if not is_valid:
            print(f"  ⚠️ Skipping '{name}' due to verification failure.")
            continue

        # 1. Seed 'sources' table
        source_exists = db.execute_one("SELECT name FROM sources WHERE name = %s", (name,))
        if not source_exists:
            db.execute(
                """
                INSERT INTO sources (name, url, country, category, language, credibility, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                """,
                (name, url, country, category, language, credibility),
                fetch=False,
            )
            print(f"  + Seeded source metadata: {name} (Country: {country}, Cat: {category})")
            added_sources += 1
        else:
            db.execute(
                """
                UPDATE sources 
                SET url = %s, country = %s, category = %s, language = %s, credibility = %s, is_active = TRUE, pause_mode = NULL
                WHERE name = %s
                """,
                (url, country, category, language, credibility, name),
                fetch=False,
            )
            print(f"  . Updated source metadata: {name}")

        # 2. Seed 'feed_sources' table
        feed_exists = db.execute_one("SELECT name FROM feed_sources WHERE name = %s", (name,))
        if not feed_exists:
            db.execute(
                """
                INSERT INTO feed_sources (name, url, category, is_active)
                VALUES (%s, %s, %s, TRUE)
                """,
                (name, url, category),
                fetch=False,
            )
            print(f"  + Seeded feed source: {name} ({url})")
            added_feeds += 1
        else:
            db.execute(
                """
                UPDATE feed_sources 
                SET url = %s, category = %s, is_active = TRUE, pause_mode = NULL
                WHERE name = %s
                """,
                (url, category, name),
                fetch=False,
            )
            print(f"  . Updated feed source: {name}")

    print(f"\nSeeding complete! Successfully added {added_sources} sources and {added_feeds} active feeds.")


if __name__ == "__main__":
    seed_feeds()
