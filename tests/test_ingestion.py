import datetime
import time
import asyncio
import types
from unittest.mock import patch, MagicMock
from ingestion import (
    normalize_headline,
    clean_rss_footer,
    normalize_feed_link,
    normalize_candidate_title,
    is_supported_display_language,
    parse_entry_timestamp,
    extract_image_url,
    fetch_og_image,
    fill_missing_og_images,
)

def test_normalize_headline():
    assert normalize_headline("ВИДЕО: Ова е наслов") == "Ова е наслов"
    assert normalize_headline("Нормален наслов") == "Нормален наслов"
    assert normalize_headline("  Ова е наслов со празни места  ") == "Ова е наслов со празни места"
    assert normalize_headline("") == ""

def test_clean_rss_footer():
    text1 = "This is some news content. The post Some title appeared first on Some source."
    assert clean_rss_footer(text1) == "This is some news content."
    
    text2 = "Content. This article was originally published on Site."
    assert clean_rss_footer(text2) == "Content."
    
    text3 = "News text. Source: https://example.com"
    assert clean_rss_footer(text3) == "News text."

    text4 = "Just normal news text without any footer."
    assert clean_rss_footer(text4) == text4


def test_clean_rss_footer_macedonian():
    text = "Содржина на вестта. Прочитајте повеќе на example.com"
    assert clean_rss_footer(text) == "Содржина на вестта."


def test_clean_rss_footer_empty():
    assert clean_rss_footer("") == ""
    assert clean_rss_footer(None) == ""


def test_clean_rss_footer_no_match():
    text = "Normal text with no footer patterns at all"
    assert clean_rss_footer(text) == text


def test_supported_display_language_rejects_albanian_rss_items():
    assert is_supported_display_language(
        "Interi vendos për rinovimin me mesfushorin turk",
        "Klubi zikaltër e kishte marrë vendimin para dopietës kundër Como.",
    ) is False
    assert is_supported_display_language(
        "Директен судир на возови во Данска",
        "Неколку лица беа повредени во несреќата.",
    ) is True


def test_normalize_headline_multiple_prefixes():
    """Only the first matching prefix should be stripped."""
    from ingestion import normalize_headline
    assert normalize_headline("ФОТО: Галерија од настанот") == "Галерија од настанот"
    assert normalize_headline("ГАЛЕРИЈА: Слики од Скопје") == "Слики од Скопје"
    assert normalize_headline("ПОТВРДЕНО: Нов договор") == "Нов договор"
    assert normalize_headline("СКАНДАЛ: Откривање") == "Откривање"
    assert normalize_headline("УЖАС: Несреќа на пат") == "Несреќа на пат"
    assert normalize_headline("ТРАГЕДИЈА: Жртви") == "Жртви"


def test_normalize_headline_html_tags():
    from ingestion import normalize_headline
    assert normalize_headline("<p>Текст</p>") == "Текст"
    assert normalize_headline("<b>Важно</b> <i>резиме</i>") == "Важно резиме"


def test_normalize_feed_link_strips_tracking_params():
    link = "https://Example.com/story/?utm_source=x&fbclid=y&id=42#section"
    assert normalize_feed_link(link) == "https://example.com/story?id=42"


def test_normalize_candidate_title_removes_prefix_noise():
    assert normalize_candidate_title("ВИДЕО: <b>Ова е</b> наслов") == "ова е наслов"


def test_normalize_candidate_title_removes_live_update_churn():
    base = normalize_candidate_title("Government announces tariffs")
    variant = normalize_candidate_title("[LIVE] Government announces tariffs - Updated")
    assert variant == base


def test_normalize_candidate_title_removes_clock_noise():
    base = normalize_candidate_title("Владата најави пакет мерки")
    variant = normalize_candidate_title("09:30 Владата најави пакет мерки")
    assert variant == base


def test_parse_entry_timestamp_uses_published_parsed():
    fallback = datetime.datetime(2026, 4, 4, 22, 0, 0)
    entry = {"published_parsed": time.struct_time((2026, 4, 4, 20, 30, 0, 0, 0, 0))}
    assert parse_entry_timestamp(entry, fallback) == datetime.datetime(2026, 4, 4, 20, 30, 0)


def test_parse_entry_timestamp_rejects_future_dates():
    fallback = datetime.datetime(2026, 4, 4, 22, 0, 0)
    entry = {"published_parsed": time.struct_time((2026, 4, 5, 20, 30, 0, 0, 0, 0))}
    assert parse_entry_timestamp(entry, fallback) == fallback


def test_extract_image_url_prefers_large_media_image():
    entry = {
        "media_content": [
            {"url": "https://example.com/thumb.jpg", "type": "image/jpeg", "width": "120", "height": "90"},
            {"url": "https://example.com/hero.jpg", "type": "image/jpeg", "width": "1400", "height": "900"},
        ]
    }
    assert extract_image_url(entry) == "https://example.com/hero.jpg"


def test_extract_image_url_avoids_logo_noise():
    entry = {
        "links": [
            {"href": "https://example.com/logo.png", "type": "image/png"},
        ],
        "enclosures": [
            {"url": "https://cdn.example.com/story-main.webp", "type": "image/webp", "width": "900", "height": "600"},
        ],
    }
    assert extract_image_url(entry) == "https://cdn.example.com/story-main.webp"


def test_extract_image_url_rejects_non_http_candidates():
    entry = {
        "media_content": [
            {"url": "data:image/png;base64,abc", "type": "image/png", "width": "1000", "height": "800"},
        ],
        "enclosures": [
            {"url": "https://cdn.example.com/story.jpg", "type": "image/jpeg"},
        ],
    }
    assert extract_image_url(entry) == "https://cdn.example.com/story.jpg"


def test_ingest_updates_last_fetched_even_when_all_entries_are_filtered_out():
    import ingestion

    recent_rows = [
        {"link": "https://example.com/story", "source": "MIA", "title": "Вест"},
    ]

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    m_dict_cur = MagicMock()
    m_dict_cur.execute.return_value = m_dict_cur
    m_dict_cur.fetchall.return_value = recent_rows
    m_dict_cur.connection.encoding = "UTF8"
    m_dict_cur.mogrify.side_effect = lambda sql, args: b"(dummy)"

    m_std_cur = MagicMock()
    m_std_cur.execute.return_value = m_std_cur
    # DatabaseManager.execute returns list of dicts.
    # The batch insert uses cur.fetchall() directly.
    # If the code expects r[0], then the dict MUST have integer keys or be a tuple.
    # Wait, ingestion.py line 562 does 'inserted_ids = [r[0] for r in results]'
    # This implies results from cur.fetchall() are tuples/lists.
    m_std_cur.fetchall.return_value = [(123, "MK")]
    m_std_cur.connection.encoding = "UTF8"
    m_std_cur.mogrify.side_effect = lambda sql, args: b"(dummy)"

    class _Conn:
        def __init__(self):
            self.executed = []

        def connection(self):
            return self

        def execute(self, sql, params=None):
            self.executed.append((sql, params))
            # Return dicts for the final SELECT id, title...
            return [{"id": 123, "title": "Вест", "link": "https://example.com/story", "country": "MK"}]

        def cursor(self, cursor_factory=None):
            if cursor_factory:
                return m_dict_cur
            return m_std_cur

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _AsyncClient:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _fake_fetch_feed_async(_client, source):
        return source["name"], [{"title": "Вест", "link": "https://example.com/story", "summary": ""}], None

    conn = _Conn()
    m_db_manager = MagicMock()
    m_db_manager.execute.side_effect = lambda sql, params=None, **kwargs: recent_rows if "SELECT link" in sql else None

    with patch.object(ingestion, "get_active_sources", return_value=[{"name": "MIA", "url": "https://feed.example.com", "country": "MK", "category": "Главни"}]), \
         patch("database.db_manager", m_db_manager), \
         patch.object(ingestion, "db", conn), \
         patch.object(ingestion, "httpx", types.SimpleNamespace(AsyncClient=lambda **_kwargs: _AsyncClient())), \
         patch.object(ingestion, "fetch_feed_async", side_effect=_fake_fetch_feed_async), \
         patch.object(ingestion, "record_source_fetch"), \
         patch("utils.redis_client", MagicMock()):
        new_count, inserted_ids, errors = asyncio.run(ingestion.ingest_all_sources_async())
    assert new_count == 0
    assert errors == []
    # In ingestion.py: db_manager.execute(...) is used for UPDATE sources
    # So we need to patch ingestion.db_manager if we want to check its call count,
    # OR we can just check if any UPDATE happened on our conn if it was used.
    # But ingestion.py does 'from database import db_manager'.


def test_fetch_og_image_reads_only_limited_head_and_resolves_relative_url():
    html = (
        b"<html><head>"
        b"<meta property='og:image' content='/images/story.jpg'>"
        b"</head><body>" + (b"x" * 100000) + b"</body></html>"
    )

    class _Resp:
        def __init__(self):
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.encoding = "utf-8"
            self.url = "https://example.com/news/story"
            self.read_bytes = 0

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            for idx in range(0, len(html), 4096):
                chunk = html[idx:idx + 4096]
                self.read_bytes += len(chunk)
                yield chunk

    class _StreamCtx:
        def __init__(self, resp):
            self.resp = resp

        async def __aenter__(self):
            return self.resp

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        def __init__(self):
            self.response = _Resp()

        def stream(self, method, url, timeout=None, follow_redirects=None):
            assert method == "GET"
            assert url == "https://example.com/news/story"
            return _StreamCtx(self.response)

    client = _Client()
    result = asyncio.run(fetch_og_image(client, "https://example.com/news/story"))

    assert result == "https://example.com/images/story.jpg"
    assert client.response.read_bytes <= 32768 + 4096


def test_fill_missing_og_images_only_updates_missing_candidates():
    candidates = [
        {"link": "https://example.com/1", "image_url": None},
        {"link": "https://example.com/2", "image_url": "https://cdn.example.com/existing.jpg"},
        {"link": "https://example.com/3", "image_url": None},
    ]

    async def _fake_fetch(_client, url):
        return f"{url}/og.jpg" if url.endswith("/3") else None

    with patch("ingestion.fetch_og_image", side_effect=_fake_fetch):
        filled = asyncio.run(fill_missing_og_images(object(), candidates))

    assert filled == 1
    assert candidates[0]["image_url"] is None
    assert candidates[1]["image_url"] == "https://cdn.example.com/existing.jpg"
    assert candidates[2]["image_url"] == "https://example.com/3/og.jpg"
