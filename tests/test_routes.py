"""
Tests for Flask API routes.
Uses Flask test client with mocked database connections.
"""
import pytest
import json
import datetime
from unittest.mock import patch, MagicMock
from collections import defaultdict


# We need to mock database and redis before importing the app
@pytest.fixture
def app():
    """Create Flask test app with mocked DB and Redis."""
    with patch('database.load_env'), \
         patch('database._db_pool', None), \
         patch('utils.redis_client') as mock_redis:

        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis.zremrangebyscore.return_value = 0
        mock_redis.zcard.return_value = 0
        mock_redis.zadd.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.pipeline.return_value = MagicMock(
            execute=MagicMock(return_value=[0, 0, 1, True])
        )

        from app import app as flask_app
        flask_app.config['TESTING'] = True
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ── View routes (template rendering) ─────────────────────────────

class TestViewRoutes:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_izvori(self, client):
        resp = client.get("/izvori")
        assert resp.status_code == 200

    def test_stats(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_archive(self, client):
        resp = client.get("/arhiva")
        assert resp.status_code == 200

    def test_briefing(self, client):
        resp = client.get("/briefing")
        assert resp.status_code == 200

    def test_about(self, client):
        resp = client.get("/about")
        assert resp.status_code == 200

    def test_privacy(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200

    def test_contact(self, client):
        resp = client.get("/contact")
        assert resp.status_code == 200

    def test_robots_txt(self, client):
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        assert b"User-agent" in resp.data

    def test_favicon(self, client):
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert "svg" in resp.content_type or "image" in resp.content_type


# ── API routes ────────────────────────────────────────────────────

class TestAPIRoutes:
    @patch('routes.api.get_db')
    def test_api_news(self, mock_get_db, client):
        mock_conn = MagicMock()
        now = datetime.datetime.now()
        article_row = {"id": 1, "cluster_id": "c1", "source": "MIA", "title": "Test",
             "link": "http://test.com", "description": "desc", "summary": None,
             "category": "Македонија", "subcategory": "", "topic": "Вести",
             "country": "🇲🇰", "created_at": now, "image_url": None,
             "clicks": 0, "original_title": "", "original_description": "",
             "is_translated": 0}

        # The api_news endpoint calls execute multiple times:
        # 1. articles query, 2. cluster_summaries, 3. reactions
        mock_conn.execute.return_value.fetchall.side_effect = [
            [article_row],   # articles
            [],              # cluster_summaries
            [],              # reactions
        ]
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/news")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "clusters" in data
        assert "total" in data
        assert "page" in data

    @patch('routes.api.get_db')
    def test_api_news_pagination(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/news?page=0&page_size=10")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["page"] == 0
        assert data["page_size"] == 10

    @patch('routes.api.get_db')
    def test_api_news_page_size_cap(self, mock_get_db, client):
        """page_size should be capped at 100."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/news?page_size=999")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["page_size"] == 100

    @patch('routes.api.get_db')
    def test_api_search_empty_query(self, mock_get_db, client):
        resp = client.get("/api/search?q=")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["clusters"] == []
        assert data["total"] == 0

    @patch('routes.api.get_db')
    def test_api_search_short_query(self, mock_get_db, client):
        resp = client.get("/api/search?q=a")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["total"] == 0

    @patch('routes.api.get_db')
    def test_api_summarize_not_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/summarize/99999")
        assert resp.status_code == 404

    @patch('routes.api.get_db')
    def test_api_summarize_cached(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {
            "id": 1, "summary": "Постоечко резиме", "title": "Test"
        }
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/summarize/1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["summary"] == "Постоечко резиме"

    @patch('routes.api.get_db')
    def test_api_analyze_not_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/analyze/nonexistent")
        assert resp.status_code == 404

    @patch('routes.api.get_db')
    def test_api_briefing_not_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/briefing")
        assert resp.status_code == 404

    @patch('routes.api.get_db')
    def test_api_briefing_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {
            "content": "Дневен брифинг",
            "date": datetime.date(2026, 3, 29)
        }
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/briefing")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["content"] == "Дневен брифинг"

    def test_api_react_invalid_emoji(self, client):
        resp = client.post("/api/react",
                          data=json.dumps({"cluster_id": "c1", "emoji": "💀"}),
                          content_type="application/json")
        assert resp.status_code == 400

    def test_api_react_missing_cluster(self, client):
        resp = client.post("/api/react",
                          data=json.dumps({"emoji": "👍"}),
                          content_type="application/json")
        assert resp.status_code == 400

    @patch('routes.api.get_db')
    def test_api_react_valid(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        resp = client.post("/api/react",
                          data=json.dumps({"cluster_id": "c1", "emoji": "👍"}),
                          content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_api_subscribe_invalid_email(self, client):
        resp = client.post("/api/subscribe",
                          data=json.dumps({"email": "notanemail"}),
                          content_type="application/json")
        assert resp.status_code == 400

    def test_api_subscribe_empty_email(self, client):
        resp = client.post("/api/subscribe",
                          data=json.dumps({"email": ""}),
                          content_type="application/json")
        assert resp.status_code == 400

    @patch('routes.api.get_db')
    def test_api_subscribe_valid(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        resp = client.post("/api/subscribe",
                          data=json.dumps({"email": "test@example.com"}),
                          content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_api_sources_reliability(self, client):
        resp = client.get("/api/sources/reliability")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "mapping" in data
        assert "default" in data
        assert data["default"] == 0.8
        assert "MIA" in data["mapping"]

    def test_api_ai_ask_short_query(self, client):
        resp = client.post("/api/ai/ask",
                          data=json.dumps({"query": "ab"}),
                          content_type="application/json")
        assert resp.status_code == 400

    def test_api_ai_ask_empty_query(self, client):
        resp = client.post("/api/ai/ask",
                          data=json.dumps({"query": ""}),
                          content_type="application/json")
        assert resp.status_code == 400

    def test_image_proxy_no_url(self, client):
        resp = client.get("/proxy")
        assert resp.status_code == 400

    def test_image_proxy_invalid_url(self, client):
        resp = client.get("/proxy?url=not-a-url")
        assert resp.status_code == 400

    @patch('routes.api.get_db')
    def test_api_top10(self, mock_get_db, client):
        mock_conn = MagicMock()
        now = datetime.datetime.now()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "cluster_id": "c1", "source": "MIA", "title": "Top News",
             "link": "http://test.com", "description": "", "summary": None,
             "category": "Македонија", "subcategory": "", "topic": "Вести",
             "country": "🇲🇰", "created_at": now, "image_url": None,
             "clicks": 5, "original_title": "", "original_description": "",
             "is_translated": 0}
        ]
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/top10")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    @patch('routes.api.get_db')
    def test_api_trending_entities(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"entity_name": "Заев", "entity_type": "PERSON", "mentions": 5}
        ]
        mock_get_db.return_value = mock_conn

        resp = client.get("/api/trending/entities")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]["entity_name"] == "Заев"


# ── Additional API routes ─────────────────────────────────────────

class TestAdditionalAPIRoutes:
    @patch('routes.api.get_db')
    def test_api_scores(self, mock_get_db, client):
        mock_conn = MagicMock()
        now = datetime.datetime.now()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "cluster_id": "c1", "source": "MIA", "title": "Score Test",
             "link": "http://test.com", "description": "", "summary": None,
             "category": "Македонија", "subcategory": "", "topic": "Вести",
             "country": "🇲🇰", "created_at": now, "image_url": None,
             "clicks": 0, "original_title": "", "original_description": "",
             "is_translated": 0}
        ]
        mock_get_db.return_value = mock_conn
        resp = client.get("/api/scores")
        assert resp.status_code == 200

    @patch('routes.api.get_db')
    def test_api_factcheck_not_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_get_db.return_value = mock_conn
        resp = client.get("/api/ai/factcheck/nonexistent")
        assert resp.status_code == 404

    def test_api_react_all_valid_emojis(self, client):
        """All allowed emojis should be accepted."""
        allowed = ["👍", "😮", "😡", "😢", "🔥"]
        for emoji in allowed:
            with patch('routes.api.get_db') as mock_get_db:
                mock_get_db.return_value = MagicMock()
                resp = client.post("/api/react",
                                  data=json.dumps({"cluster_id": "c1", "emoji": emoji}),
                                  content_type="application/json")
                assert resp.status_code == 200, f"Emoji {emoji} should be accepted"


# ── View routes with DB ───────────────────────────────────────────

class TestViewRoutesWithDB:
    @patch('routes.views.get_db')
    def test_cluster_page_not_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_get_db.return_value = mock_conn
        resp = client.get("/cluster/nonexistent")
        assert resp.status_code == 404

    @patch('routes.views.get_db')
    def test_source_page_not_found(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_get_db.return_value = mock_conn
        resp = client.get("/izvor/NonexistentSource")
        assert resp.status_code == 404

    @patch('routes.views.get_db')
    def test_og_image(self, mock_get_db, client):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = [42]
        mock_get_db.return_value = mock_conn
        resp = client.get("/og-image.svg")
        assert resp.status_code == 200
        assert "svg" in resp.content_type


# ── Rate limiting ─────────────────────────────────────────────────

class TestRateLimiting:
    @patch('app.check_rate_limit', return_value=False)
    def test_rate_limited_returns_429(self, mock_rl, client):
        resp = client.get("/api/sources/reliability")
        assert resp.status_code == 429

    def test_static_routes_skip_rate_limit(self, client):
        """Root and static paths should bypass rate limiting."""
        resp = client.get("/")
        assert resp.status_code == 200  # Not 429


# ── Security headers ──────────────────────────────────────────────

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/about")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
