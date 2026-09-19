"""Seed the active Macedonian feed catalog used by the ingestion worker."""

from core.database import db_manager as db


MK_FEEDS = [
    ("MIA", "https://mia.mk/rss"),
    ("Telma", "https://telma.com.mk/feed/"),
    ("SDK", "https://sdk.mk/feed/"),
    ("360 Stepeni", "https://360stepeni.mk/feed/"),
    ("Meta.mk", "https://meta.mk/feed/"),
    ("Sloboden Pecat", "https://slobodenpecat.mk/feed/"),
    ("Fokus", "https://fokus.mk/feed/"),
    ("Faktor", "https://faktor.mk/rss"),
    ("Kurir", "https://kurir.mk/feed/"),
    ("Vecer", "https://vecer.mk/feed/"),
    ("Republika", "https://republika.mk/feed/"),
    ("TV21", "https://tv21.tv/mk/feed/"),
    ("Kanal 5", "https://kanal5.com.mk/feed/"),
    ("Sitel", "https://sitel.com.mk/rss.xml"),
    ("OhridNews", "https://ohridnews.com/feed/"),
    ("A1on", "https://a1on.mk/feed/"),
    ("Nezavisen", "https://nezavisen.mk/feed/"),
    ("Plusinfo", "https://plusinfo.mk/feed/"),
]


def seed_mk_feed_sources() -> None:
    for name, url in MK_FEEDS:
        db.execute(
            """
            INSERT INTO sources (name, url, country, category, is_active)
            VALUES (%s, %s, 'MK', 'Makedonija', TRUE)
            ON CONFLICT (name) DO UPDATE SET
                url = EXCLUDED.url,
                country = 'MK',
                is_active = TRUE
            """,
            (name, url),
            fetch=False,
        )
        db.execute(
            """
            INSERT INTO feed_sources (name, url, category, is_active)
            VALUES (%s, %s, 'Makedonija', TRUE)
            ON CONFLICT (name) DO UPDATE SET
                url = EXCLUDED.url,
                category = EXCLUDED.category,
                is_active = TRUE
            """,
            (name, url),
            fetch=False,
        )
    print(f"Seeded {len(MK_FEEDS)} Macedonian feed sources.")


if __name__ == "__main__":
    seed_mk_feed_sources()
