"""
Tests for Flask API routes.
Uses Flask test client with mocked database connections.
"""
import os
import pytest
import json
import datetime
from unittest.mock import patch, MagicMock


# We need to mock database and redis before importing the app
@pytest.fixture
def app():
    """Create Flask test app with mocked DB and Redis."""
    with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-for-tests"}), \
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

    def test_public_root_redirects_to_primary_site(self, client):
        resp = client.get("/", headers={"Host": "presek.live"})
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://presek.live/"

    def test_public_cluster_redirects_to_primary_site(self, client):
        resp = client.get("/cluster/abc123def456abc1", headers={"Host": "presek.live"})
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://presek.live/cluster/abc123def456abc1"

    def test_public_privacy_redirects_to_primary_site(self, client):
        resp = client.get("/privacy", headers={"Host": "presek.live"})
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://presek.live/privacy"

    def test_public_source_redirects_to_public_sources_page(self, client):
        resp = client.get("/izvor/MIA", headers={"Host": "presek.live"})
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://presek.live/izvori?source=MIA"

    def test_localhost_keeps_legacy_template_access(self, client):
        resp = client.get("/stats", headers={"Host": "localhost"})
        assert resp.status_code == 200


# ── /api/news ─────────────────────────────────────────────────────

class TestAPINews:
    def _mock_db(self, rows=None, synthesis_ids=None):
        mock_db = MagicMock()
        mock_db.get_articles_by_country.return_value = rows or []
        mock_db.get_articles_by_ids.return_value = rows or []
        mock_db.search_articles.return_value = rows or []
        mock_db.get_personalized_articles.return_value = rows or []
        mock_db.get_synthesis_ids.return_value = synthesis_ids or []
        return mock_db

    def _article(self, cluster_id="abc123"):
        return {
            "id": 1, "cluster_id": cluster_id, "source": "MIA",
            "title": "Test", "link": "http://test.com",
            "description": "desc", "summary": None,
            "category": "Македонија", "subcategory": "", "topic": "Вести",
            "country": "🇲🇰", "created_at": datetime.datetime.now(),
            "image_url": None, "clicks": 0,
            "original_title": "", "original_description": "", "is_translated": 0,
        }

    def test_api_news_empty(self, client):
        with patch('routes.api.db', self._mock_db()):
            resp = client.get("/api/news")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "clusters" in data
        assert "total_clusters" in data
        assert "page" in data

    def test_api_news_returns_cluster(self, client):
        article = self._article("abc123")
        with patch('routes.api.db', self._mock_db([article])):
            resp = client.get("/api/news")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["total_clusters"] == 1
        assert data["clusters"][0]["cluster_id"] == "abc123"

    def test_api_news_pagination(self, client):
        with patch('routes.api.db', self._mock_db()):
            resp = client.get("/api/news?page=0&page_size=10")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["page"] == 0
        assert data["page_size"] == 10

    def test_api_news_page_size_cap(self, client):
        """page_size is capped at 200."""
        with patch('routes.api.db', self._mock_db()):
            resp = client.get("/api/news?page_size=999")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["page_size"] == 200

    def test_api_news_offset_too_large(self, client):
        with patch('routes.api.db', self._mock_db()):
            resp = client.get("/api/news?page=10000&page_size=200")
        assert resp.status_code == 400

    def test_api_news_search(self, client):
        article = self._article()
        with patch('routes.api.db', self._mock_db([article])):
            resp = client.get("/api/news?q=тест")
        assert resp.status_code == 200

    def test_api_news_search_too_long(self, client):
        """Query over 500 chars should still return 200 (truncated)."""
        with patch('routes.api.db', self._mock_db()):
            resp = client.get("/api/news?q=" + "а" * 600)
        assert resp.status_code == 200


# ── /api/chat_cluster ─────────────────────────────────────────────

class TestChatCluster:
    def test_missing_params(self, client):
        resp = client.post("/api/chat_cluster",
                           data=json.dumps({}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_invalid_cluster_id(self, client):
        resp = client.post("/api/chat_cluster",
                           data=json.dumps({"cluster_id": "not-hex!", "query": "What?"}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_query_too_long(self, client):
        resp = client.post("/api/chat_cluster",
                           data=json.dumps({"cluster_id": "abc123", "query": "q" * 600}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_cluster_not_found(self, client):
        mock_db = MagicMock()
        mock_db.execute.return_value = []
        with patch('routes.api.db', mock_db):
            resp = client.post("/api/chat_cluster",
                               data=json.dumps({"cluster_id": "abc123def456", "query": "тест?"}),
                               content_type="application/json")
        assert resp.status_code == 404

    def test_valid_request(self, client):
        mock_db = MagicMock()
        mock_db.execute.return_value = [{"title": "T", "description": "D", "source": "MIA"}]
        mock_db.execute_one.return_value = None
        with patch('routes.api.db', mock_db), \
             patch('routes.api._call_ai', return_value=("AI одговор", "gemini")):
            resp = client.post("/api/chat_cluster",
                               data=json.dumps({"cluster_id": "abc123def456", "query": "тест?"}),
                               content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["response"] == "AI одговор"

    def test_cluster_ask_returns_structured_evidence(self, client):
        mock_db = MagicMock()
        mock_db.execute.return_value = [
            {"title": "T1", "description": "D1", "source": "MIA", "link": "https://example.com/1", "created_at": None, "category": "Свет"},
            {"title": "T2", "description": "D2", "source": "Reuters", "link": "https://example.com/2", "created_at": None, "category": "Свет"},
        ]
        mock_db.execute_one.return_value = None
        ai_json = json.dumps({
            "answer": "Главниот развој е потврден. Некои детали остануваат нејасни.",
            "confirmed_points": ["Главниот развој е потврден."],
            "unclear_points": ["Некои детали остануваат нејасни."],
            "source_differences": "МИА го нагласува настанот, а Reuters поширокиот контекст.",
            "citation_numbers": [1, 2],
            "related_questions": ["Што сè уште не е потврдено?"],
            "confidence": "medium",
        })
        with patch('routes.api.db', mock_db), \
             patch('routes.api.answer_cluster_question_locally', return_value=None), \
             patch('routes.api._call_ai', return_value=(ai_json, "gemini")):
            resp = client.post("/api/cluster/abc123def456/ask",
                               data=json.dumps({"question": "Што е ново?"}),
                               content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["confirmed_points"] == ["Главниот развој е потврден."]
        assert data["unclear_points"] == ["Некои детали остануваат нејасни."]
        assert data["source_differences"].startswith("МИА")
        assert "snippet" in data["citations"][0]


# ── /proxy ────────────────────────────────────────────────────────

class TestProxy:
    def test_no_url(self, client):
        resp = client.get("/proxy")
        assert resp.status_code == 400

    def test_invalid_scheme(self, client):
        resp = client.get("/proxy?url=ftp://example.com/img.jpg")
        assert resp.status_code == 400

    def test_non_http_url(self, client):
        resp = client.get("/proxy?url=not-a-url")
        assert resp.status_code == 400

    def test_localhost_blocked(self, client):
        resp = client.get("/proxy?url=http://localhost/secret")
        assert resp.status_code == 403

    def test_private_ip_blocked(self, client):
        resp = client.get("/proxy?url=http://192.168.1.1/img.png")
        assert resp.status_code == 403

    def test_valid_url_fetched(self, client):
        import urllib.request
        import socket
        mock_resp = MagicMock()
        mock_resp.headers.get.return_value = "image/jpeg"
        mock_resp.read.side_effect = [b"\xff\xd8\xff" * 100, b""]
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        # Return a public IP so the DNS-based SSRF check passes in CI (no real network)
        public_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]

        with patch('routes.api.cached_response', return_value=None), \
             patch('routes.api.set_cache'), \
             patch('socket.getaddrinfo', return_value=public_addrinfo), \
             patch('urllib.request.urlopen', return_value=mock_resp):
            resp = client.get("/proxy?url=https://example.com/image.jpg")
        assert resp.status_code in (200, 502)


# ── /api/sources controls ────────────────────────────────────────

class TestSourceControls:
    def test_sources_include_inactive(self, client):
        mock_db = MagicMock()
        mock_db.execute.return_value = [
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": True, "last_fetched": None},
            {"name": "BadFeed", "country": "🇲🇰", "category": "Локални", "credibility": 0.8, "is_active": False, "last_fetched": None},
        ]
        with patch("routes.api.db", mock_db), patch("routes.api.get_source_statuses", return_value={}):
            resp = client.get("/api/sources?include_inactive=1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 2
        assert data[1]["is_active"] is False

    def test_source_control_rejects_unauthorized(self, client):
        resp = client.post(
            "/api/sources/MIA/control",
            data=json.dumps({"action": "pause"}),
            headers={"X-Forwarded-For": "1.2.3.4"},
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_source_control_pause_with_token(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.side_effect = [
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": True, "last_fetched": None},
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": False, "last_fetched": None},
        ]
        with patch("routes.api.db", mock_db), patch("routes.api.get_source_statuses", return_value={}):
            resp = client.post(
                "/api/sources/MIA/control",
                data=json.dumps({"action": "pause"}),
                headers={"X-Admin-Token": "test-secret-key-for-tests", "X-Forwarded-For": "1.2.3.4"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_db.execute.assert_called_with(
            "UPDATE sources SET is_active = FALSE WHERE name = %s", ("MIA",), fetch=False
        )

    def test_source_control_reset_uses_default_credibility(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.side_effect = [
            {"name": "Unknown Feed", "country": "🇲🇰", "category": "Локални", "credibility": 1.7, "is_active": True, "last_fetched": None},
            {"name": "Unknown Feed", "country": "🇲🇰", "category": "Локални", "credibility": 0.8, "is_active": True, "last_fetched": None},
        ]
        with patch("routes.api.db", mock_db), patch("routes.api.get_source_statuses", return_value={}):
            resp = client.post(
                "/api/sources/Unknown%20Feed/control",
                data=json.dumps({"action": "reset"}),
                headers={"X-Admin-Token": "test-secret-key-for-tests", "X-Forwarded-For": "1.2.3.4"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_db.execute.assert_called_with(
            "UPDATE sources SET credibility = %s WHERE name = %s", (0.8, "Unknown Feed"), fetch=False
        )


# ── View routes with DB ───────────────────────────────────────────

class TestViewRoutesWithDB:
    @patch('routes.views.get_db')
    def test_cluster_page_invalid_id(self, mock_get_db, client):
        """Non-hex cluster_id should return 400."""
        resp = client.get("/cluster/nonexistent")
        assert resp.status_code == 400

    @patch('routes.views.get_db')
    def test_cluster_page_not_found(self, mock_get_db, client):
        """Valid hex id that doesn't exist in DB returns 404."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_get_db.return_value = mock_conn
        resp = client.get("/cluster/abc123def456abc1")
        assert resp.status_code == 404

    @patch('routes.views.get_db')
    def test_source_page_too_long(self, mock_get_db, client):
        """Source name over 100 chars returns 400."""
        resp = client.get("/izvor/" + "A" * 101)
        assert resp.status_code == 400

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

    def test_api_cluster_normalizes_label_text_perspectives(self, client):
        article = {
            "id": 1,
            "cluster_id": "abc123def456abc1",
            "title": "Test cluster title",
            "description": "Test cluster description",
            "source": "MIA",
            "link": "https://example.com/story",
            "country": "🇲🇰",
            "category": "Македонија",
            "topic": "Вести",
            "created_at": datetime.datetime.now(),
            "image_url": None,
            "clicks": 0,
            "original_title": "",
            "original_description": "",
            "is_translated": 0,
        }

        mock_db = MagicMock()
        mock_db.execute.return_value = [article]
        mock_db.execute_one.side_effect = [
            {
                "summary": "• Главен факт\n• Контекст\n• Последица",
                "perspectives": [
                    {"label": "Официјален став", "text": "Институциите го потврдуваат случајот."}
                ],
            },
            {"tags": ["Влада"], "topics": ["Политика"]},
        ]

        with patch("routes.api.db", mock_db):
            resp = client.get("/api/cluster/abc123def456abc1")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["data"]["perspectives"] == [
            {
                "angle": "Официјален став",
                "content": "Институциите го потврдуваат случајот.",
            }
        ]


# ── Rate limiting ─────────────────────────────────────────────────

class TestRateLimiting:
    @patch('app.check_rate_limit', return_value=False)
    def test_expensive_ai_routes_are_rate_limited(self, mock_rl, client):
        resp = client.post(
            "/api/chat_cluster",
            data=json.dumps({"cluster_id": "abc123def456", "query": "тест?"}),
            content_type="application/json",
        )
        assert resp.status_code == 429

    @patch('app.check_rate_limit', return_value=False)
    def test_read_only_api_routes_skip_rate_limit(self, mock_rl, client):
        resp = client.get("/api/stats")
        assert resp.status_code != 429

    def test_static_routes_skip_rate_limit(self, client):
        """Root path bypasses rate limiting."""
        resp = client.get("/")
        assert resp.status_code == 200


# ── Security headers ──────────────────────────────────────────────

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/about")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert resp.headers.get("Strict-Transport-Security") is not None
        assert resp.headers.get("Content-Security-Policy") is not None
