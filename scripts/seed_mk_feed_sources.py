"""Seed the active Macedonian feed catalog used by the ingestion worker."""

from core.database import db_manager as db


MK_FEEDS = [
    # Core national outlets.
    ("360 Stepeni", "https://360stepeni.mk/feed/"),
    ("A1on", "https://a1on.mk/feed/"),
    ("Faktor", "https://faktor.mk/feed/"),
    ("Fokus", "https://fokus.mk/feed/"),
    ("Kanal 5", "https://kanal5.com.mk/rss.aspx"),
    ("Kurir", "https://kurir.mk/feed/"),
    ("Meta.mk", "https://meta.mk/feed/"),
    ("MIA", "https://mia.mk/feed/"),
    ("Nezavisen", "https://nezavisen.mk/feed/"),
    ("OhridNews", "https://ohridnews.com/feed/"),
    ("Plusinfo", "https://plusinfo.mk/feed/"),
    ("Republika", "https://republika.mk/feed/"),
    ("Sitel", "https://sitel.com.mk/rss.xml"),
    ("Telma", "https://telma.com.mk/feed/"),
    ("Vecer", "https://vecer.mk/feed/"),
    # Added from the time.mk source index (fresh + Macedonian feeds verified).
    ("4News", "https://4news.mk/feed/"),
    ("Biznis Vesti", "https://biznisvesti.mk/feed/"),
    ("Brif", "https://brif.mk/feed/"),
    ("Civil Media", "https://civilmedia.mk/feed/"),
    ("eMagazin", "https://emagazin.mk/feed/"),
    ("Frontline", "https://frontline.mk/feed/"),
    ("Infomax", "https://infomax.mk/feed/"),
    ("Kajgana", "https://kajgana.com/rss.xml"),
    ("Libertas", "https://libertas.mk/feed/"),
    ("Makfax", "https://makfax.com.mk/feed/"),
    ("Nova Makedonija", "https://novamakedonija.com.mk/feed/"),
    ("Ohrid1", "https://ohrid1.com/feed/"),
    ("Pari", "https://pari.com.mk/feed/"),
    ("Politika", "https://politika.com.mk/feed/"),
    ("Press24", "https://press24.mk/feed/"),
    ("Provereno", "https://provereno.mk/feed/"),
    ("Puls24", "https://puls24.mk/feed/"),
    ("Racin", "https://racin.mk/feed/"),
    ("Radio MOF", "https://radiomof.mk/feed/"),
    ("Religija", "https://religija.mk/feed/"),
    ("Skopje1", "https://skopje1.mk/feed/"),
    ("Skopsko Eho", "https://skopskoeho.mk/feed/"),
    ("Zurnal", "https://zurnal.mk/feed/"),
    # Sport.
    ("MakFudbal", "https://makfudbal.mk/feed/"),
    ("SportMedia", "https://sportmedia.mk/feed/"),
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
