
import asyncio
import logging
import feedparser
import httpx
from nllb_translate import translate as nllb_translate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.regional_prototype")

REGIONAL_FEEDS = [
    ("B92 (RS)", "https://www.b92.net/info/rss/vesti.xml", "sr"),
    ("Dnevnik.bg (BG)", "https://www.dnevnik.bg/rss/", "bg"),
    ("Index.hr (HR)", "https://www.index.hr/rss", "hr")
]

async def prototype_regional_ingest():
    print("\n--- Presek Regional News Prototype (NLLB-200) ---")
    print("Goal: Ingest and translate Balkan news into Macedonian.\n")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, url, lang in REGIONAL_FEEDS:
            print(f"📡 Fetching from {name} [{lang}]...")
            try:
                resp = await client.get(url)
                feed = feedparser.parse(resp.text)
                
                # Take top 2 items from each
                for entry in feed.entries[:2]:
                    orig_title = entry.title
                    print(f"  [Original] {orig_title}")
                    
                    # Use NLLB to translate to Macedonian
                    # nllb_translate(text, src_lang, target_lang)
                    translated = nllb_translate(orig_title, src_lang=lang, target_lang="mk")
                    
                    if translated:
                        print(f"  ✨ [Macedonian] {translated}")
                    else:
                        print("  ❌ [Macedonian] Translation failed.")
                    print("-" * 20)
                    
            except Exception as e:
                print(f"  FAILED to fetch {name}: {e}")
            print("\n")

if __name__ == "__main__":
    asyncio.run(prototype_regional_ingest())
