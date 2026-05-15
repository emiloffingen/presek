import feedparser
import httpx

def test_rss(url):
    print(f"Testing {url}...")
    try:
        resp = httpx.get(url, timeout=15.0, follow_redirects=True)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            feed = feedparser.parse(resp.content)
            print(f"  Bozo: {feed.bozo}")
            print(f"  Entries: {len(feed.entries)}")
            if feed.entries:
                print(f"  Latest title: {feed.entries[0].title}")
        else:
            print(f"  Error content: {resp.text[:100]}")
    except Exception as e:
        print(f"  Exception: {e}")

if __name__ == "__main__":
    test_rss("https://www.kurir.rs/rss/")
    test_rss("https://www.danas.rs/feed/")
    test_rss("https://n1info.rs/feed/")
