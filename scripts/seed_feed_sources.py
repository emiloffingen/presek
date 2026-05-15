from core.database import db_manager as db

# Serbian News Catalog (80 Sources)
SERBIAN_FEED_CATALOG = [
    # Mainstream / Tabloid
    ("Blic", "https://www.blic.rs/rss/danasnje-vesti"),
    ("Kurir", "https://www.kurir.rs/rss/"),
    ("Telegraf", "https://www.telegraf.rs/rss"),
    ("Informer", "https://informer.rs/rss/vesti/sve"),
    ("Alo", "https://www.alo.rs/rss/sve-vesti"),
    ("Mondo", "https://mondo.rs/rss/1/Sve-vesti"),
    ("Srbija danas", "https://www.srbijadanas.com/rss/sve-vesti"),
    ("Republika", "https://www.republika.rs/rss/sve-vesti"),
    ("Novosti", "https://www.novosti.rs/rss"),
    ("Objektiv", "https://objektiv.rs/feed/"),
    ("Espreso", "https://www.espreso.co.rs/rss"),
    ("Kurir Sport", "https://www.kurir.rs/rss/Sport"),
    ("Telegraf Sport", "https://www.telegraf.rs/rss/Sport"),
    ("Mozzart Sport", "https://www.mozzartsport.com/rss"),

    # Independent / Public / Analytical
    ("N1 Info", "https://n1info.rs/feed/"),
    ("nova.rs", "https://nova.rs/feed/"),
    ("danas", "https://www.danas.rs/feed/"),
    ("RTS", "https://www.rts.rs/page/stories/sr/rss.html"),
    ("B92", "https://www.b92.net/info/rss/vesti.xml"),
    ("Politika", "https://www.Politika.rs/rss/"),
    ("Vreme", "https://www.vreme.com/feed/"),
    ("NIN", "https://www.nin.rs/rss"),
    ("Nedeljnik", "https://www.nedeljnik.rs/feed/"),
    ("Insajder", "https://insajder.net/rss/vesti"),
    ("KRIK", "https://www.krik.rs/feed/"),
    ("CINS", "https://www.cins.rs/feed/"),
    ("BIRN", "https://birn.eu.com/feed/"),
    ("Euronews Srbija", "https://euronews.rs/rss"),
    ("Tanjug", "https://www.tanjug.rs/rss"),
    ("BBC News na srpskom", "https://www.bbc.com/serbian/lat/index.xml"),
    ("Radio Slobodna Evropa", "https://www.slobodnaevropa.org/api/z_opegvi_e_"),
    ("Peščanik", "https://pescanik.net/feed/"),
    ("Autonomija", "https://autonomija.info/feed/"),
    ("Cenzolovka", "https://cenzolovka.rs/feed/"),
    ("Direktno", "https://direktno.rs/rss"),
    ("Istinomer", "https://www.istinomer.rs/feed/"),
    ("Mašina", "https://www.masina.rs/feed/"),

    # Regional
    ("021.rs", "https://www.021.rs/rss/Sve-vesti"),
    ("RTV", "https://rtv.rs/sr_lat/rss/"),
    ("Južne vesti", "https://www.juznevesti.com/rss/"),
    ("Glas Šumadije", "https://glassumadije.rs/feed/"),
    ("Subotica.com", "https://www.subotica.com/rss.xml"),
    ("Bujanovačke", "https://bujanovacke.co.rs/feed/"),
    ("InfoKG", "https://infokg.rs/feed/"),
    ("OZON Press", "https://ozonpress.net/feed/"),
    ("Oglasna Tabla", "https://oglasnatabla.rs/feed/"),
    ("Vranje News", "https://vranjenews.rs/feed/"),
    ("Moravski", "https://moravski.rs/feed/"),
    ("Jugmedia", "https://jugmedia.rs/feed/"),
    ("Zaječarska Hronika", "https://zamedia.rs/feed/"),
    ("Kruševac PRESS", "https://krusevacpress.com/feed/"),
    ("Šabac PRESS", "https://sabacpress.com/feed/"),
    ("Užička Republika", "https://uzickarepublika.rs/feed/"),
    ("Sombor Info", "https://soinfo.org/feed/"),
    ("Pirotske vesti", "https://www.pirotskevesti.rs/feed/"),
    ("Kraljevo Online", "https://kraljevo.online/feed/"),
    ("Valjevska posla", "https://valjevskaposla.rs/feed/"),

    # Thematic / Lifestyle / Tech / Cultural
    ("BenchMark", "https://benchmark.rs/feed/"),
    ("PC Press", "https://pcpress.rs/feed/"),
    ("Netokracija", "https://netokracija.rs/feed/"),
    ("Kulturni centar Beograda", "https://www.kcb.org.rs/feed/"),
    ("Oblakoder", "https://oblakoder.org.rs/feed/"),
    ("City Magazine", "https://citymagazine.danas.rs/feed/"),
    ("Before After", "https://beforeafter.rs/feed/"),
    ("Wannabe Magazine", "https://wannabemagazine.com/feed/"),
    ("Lola Magazin", "https://lolamagazin.com/feed/"),
    ("Zadovoljna", "https://zadovoljna.nova.rs/feed/"),
    ("Biznis.rs", "https://biznis.rs/feed/"),
    ("Ekapija", "https://www.ekapija.com/rss/sr"),
    ("Kamatica", "https://www.kamatica.com/feed/"),
    ("Poljoprivrednik", "https://poljoprivrednik.net/feed/"),
    ("Agrosmart", "https://agrosmart.net/feed/"),
    ("Sportski žurnal", "https://zurnal.rs/rss"),
    ("HotSport", "https://hotsport.rs/feed/"),
    ("MaxBet Sport", "https://maxbetsport.rs/feed/"),
    ("Espreso Sport", "https://www.espreso.co.rs/rss/Sport"),
    ("Kosovo Online", "https://www.kosovo-online.com/rss.xml"),
    ("Sputnjik Srbija", "https://sputnikportal.rs/rss/index.xml"),
    ("Tanjug Biznis", "https://www.tanjug.rs/rss/biznis"),
]

def seed_feed_sources():
    print(f"Seeding {len(SERBIAN_FEED_CATALOG)} Serbian feed sources into the 'feed_sources' table...")
    
    added = 0
    updated = 0
    
    for name, url in SERBIAN_FEED_CATALOG:
        exists = db.execute_one("SELECT name FROM feed_sources WHERE name = %s", (name,))
        if not exists:
            db.execute(
                "INSERT INTO feed_sources (name, url, is_active) VALUES (%s, %s, %s)",
                (name, url, True),
                fetch=False,
            )
            added += 1
            print(f"  + Added feed source: {name}")
        else:
            db.execute(
                "UPDATE feed_sources SET url = %s WHERE name = %s",
                (url, name),
                fetch=False,
            )
            updated += 1
            print(f"  . Updated feed source: {name}")
            
    print(f"Sync complete. Added {added}, updated {updated} feed sources.")

if __name__ == "__main__":
    seed_feed_sources()
