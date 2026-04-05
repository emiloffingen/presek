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
    with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-for-tests", "PRESEK_ADMIN_TOKEN": "test-admin-token"}), \
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

    def test_briefing_format_escapes_html(self, app):
        formatter = app.jinja_env.filters["briefing_format"]
        rendered = str(formatter("## Наслов\n<script>alert(1)</script>\n- <b>точка</b>"))
        assert "<script>" not in rendered
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
        assert "&lt;b&gt;точка&lt;/b&gt;" in rendered


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

    def test_cluster_ask_falls_back_when_ai_path_throws(self, client):
        mock_db = MagicMock()
        mock_db.execute.return_value = [
            {"title": "T1", "description": "D1", "source": "MIA", "link": "https://example.com/1", "created_at": None, "category": "Свет"},
            {"title": "T2", "description": "D2", "source": "Reuters", "link": "https://example.com/2", "created_at": None, "category": "Свет"},
        ]
        mock_db.execute_one.return_value = None
        with patch('routes.api.db', mock_db), \
             patch('routes.api.answer_cluster_question_locally', side_effect=RuntimeError("boom")), \
             patch('routes.api._call_ai', side_effect=RuntimeError("boom")):
            resp = client.post("/api/cluster/abc123def456/ask",
                               data=json.dumps({"question": "Што е ново?"}),
                               content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["answer"]
        assert data["confidence"] in {"low", "medium", "high"}


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
        import socket
        import types

        class FakeImage:
            mode = "RGB"
            width = 10
            height = 10

            def convert(self, _mode):
                return self

            def resize(self, _size, _resampling):
                return self

            def save(self, fp, _format, quality=None, method=None):
                fp.write(b"webp-bytes")

        fake_image_module = types.SimpleNamespace(
            open=MagicMock(return_value=FakeImage()),
            Resampling=types.SimpleNamespace(LANCZOS="LANCZOS"),
        )
        fake_pil_module = types.SimpleNamespace(Image=fake_image_module)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers.get.return_value = "image/png"
        mock_resp.iter_content.return_value = [b"png-bytes"]
        mock_resp.raw.connection.sock.getpeername.return_value = ("93.184.216.34", 443)

        # Return a public IP so the DNS-based SSRF check passes in CI (no real network)
        public_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch('routes.api.cached_response', return_value=None), \
             patch('routes.api.set_cache'), \
             patch('socket.getaddrinfo', return_value=public_addrinfo), \
             patch.dict('sys.modules', {'PIL': fake_pil_module, 'PIL.Image': fake_image_module}), \
             patch('requests.Session', return_value=mock_session):
            resp = client.get("/proxy?url=https://example.com/image.jpg")
        assert resp.status_code == 200
        assert resp.content_type == "image/webp"


# ── /api/sources controls ────────────────────────────────────────

class TestSourceControls:
    def test_sources_include_inactive(self, client):
        mock_db = MagicMock()
        mock_db.execute.return_value = [
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": True, "last_fetched": None, "pause_mode": None, "pause_reason": None, "paused_at": None},
            {"name": "BadFeed", "country": "🇲🇰", "category": "Локални", "credibility": 0.8, "is_active": False, "last_fetched": None, "pause_mode": "auto", "pause_reason": "Repeated ingestion failures", "paused_at": None},
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
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": True, "last_fetched": None, "pause_mode": None, "pause_reason": None, "paused_at": None},
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": False, "last_fetched": None, "pause_mode": "manual", "pause_reason": "Manual pause", "paused_at": None},
        ]
        with patch("routes.api.db", mock_db), patch("routes.api.get_source_statuses", return_value={}):
            resp = client.post(
                "/api/sources/MIA/control",
                data=json.dumps({"action": "pause"}),
                headers={"X-Admin-Token": "test-admin-token", "X-Forwarded-For": "1.2.3.4"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_db.execute.assert_called_with(
            "UPDATE sources SET is_active = FALSE, pause_mode = 'manual', pause_reason = %s, paused_at = NOW() WHERE name = %s",
            ("Manual pause", "MIA"),
            fetch=False
        )

    def test_source_control_reset_uses_default_credibility(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.side_effect = [
            {"name": "Unknown Feed", "country": "🇲🇰", "category": "Локални", "credibility": 1.7, "is_active": True, "last_fetched": None, "pause_mode": None, "pause_reason": None, "paused_at": None},
            {"name": "Unknown Feed", "country": "🇲🇰", "category": "Локални", "credibility": 0.8, "is_active": True, "last_fetched": None, "pause_mode": None, "pause_reason": None, "paused_at": None},
        ]
        with patch("routes.api.db", mock_db), patch("routes.api.get_source_statuses", return_value={}), patch("routes.api.reset_source_policy"):
            resp = client.post(
                "/api/sources/Unknown%20Feed/control",
                data=json.dumps({"action": "reset"}),
                headers={"X-Admin-Token": "test-admin-token", "X-Forwarded-For": "1.2.3.4"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_db.execute.assert_called_with(
            "UPDATE sources SET credibility = %s, pause_mode = NULL, pause_reason = NULL, paused_at = NULL WHERE name = %s",
            (0.8, "Unknown Feed"),
            fetch=False
        )

    def test_source_control_rejects_secret_key_token(self, client):
        with patch.dict(os.environ, {"PRESEK_ADMIN_TOKEN": "", "SECRET_KEY": "test-secret-key-for-tests"}):
            resp = client.post(
                "/api/sources/MIA/control",
                data=json.dumps({"action": "pause"}),
                headers={"X-Admin-Token": "test-secret-key-for-tests", "X-Forwarded-For": "1.2.3.4"},
                content_type="application/json",
            )
        assert resp.status_code == 403


class TestProfileSync:
    def test_profile_sync_init(self, client):
        mock_db = MagicMock()
        with patch("routes.api.db", mock_db), patch("routes.api.secrets.token_urlsafe", return_value="sync-token-123"):
            resp = client.post("/api/profile/sync/init")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "success"
        assert data["token"] == "sync-token-123"

    def test_profile_sync_get(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.return_value = {
            "profile_data": {
                "followedTopics": ["Политика"],
                "followedSources": ["MIA"],
                "recentClusters": [{"cluster_id": "abc", "viewedAt": "2026-04-05T10:00:00Z"}],
                "deliveryPreferences": {"morningBriefing": False},
            },
            "updated_at": "2026-04-05T10:00:00Z",
        }
        with patch("routes.api.db", mock_db):
            resp = client.get("/api/profile/sync?token=sync-token-123")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["profile"]["followedTopics"] == ["Политика"]
        assert data["profile"]["deliveryPreferences"]["morningBriefing"] is False

    def test_profile_sync_save_merges(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.return_value = {
            "profile_data": {
                "followedTopics": ["Политика"],
                "followedSources": [],
                "recentClusters": [],
                "deliveryPreferences": {"morningBriefing": True, "breakingAlerts": True, "browserPermission": "default"},
            }
        }
        payload = {
            "token": "sync-token-123",
            "profile": {
                "followedTopics": ["Економија"],
                "followedSources": ["Телма"],
                "recentClusters": [{"cluster_id": "xyz", "viewedAt": "2026-04-05T11:00:00Z"}],
                "deliveryPreferences": {"morningBriefing": False, "breakingAlerts": True, "browserPermission": "granted"},
            },
        }
        with patch("routes.api.db", mock_db):
            resp = client.post("/api/profile/sync", data=json.dumps(payload), content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["profile"]["followedTopics"] == ["Политика", "Економија"]
        assert data["profile"]["followedSources"] == ["Телма"]

    def test_profile_delivery_get(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.side_effect = [
            {"exists": 1},
            {
                "channel": "ntfy",
                "target": "reader-feed",
                "morning_briefing": True,
                "weekly_digest": True,
                "breaking_topics": True,
                "breaking_sources": False,
                "is_active": True,
                "updated_at": "2026-04-05T10:00:00Z",
            },
        ]
        with patch("routes.api.db", mock_db):
            resp = client.get("/api/profile/delivery?token=sync-token-123")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["subscription"]["target"] == "reader-feed"
        assert data["subscription"]["weeklyDigest"] is True
        assert data["subscription"]["breakingTopics"] is True

    def test_profile_delivery_save(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.return_value = {"exists": 1}
        payload = {
            "token": "sync-token-123",
            "subscription": {
                "target": "reader-feed",
                "morningBriefing": True,
                "weeklyDigest": True,
                "breakingTopics": True,
                "breakingSources": True,
                "isActive": True,
            },
        }
        with patch("routes.api.db", mock_db):
            resp = client.post("/api/profile/delivery", data=json.dumps(payload), content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["subscription"]["target"] == "reader-feed"
        assert data["subscription"]["weeklyDigest"] is True
        assert data["subscription"]["breakingSources"] is True


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


class TestStatsFull:
    def test_stats_full_includes_editor_analytics(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.side_effect = [
            {"count": 1200},
            {"count": 180},
            {"count": 600},
            {"mb": 256.4},
            {"n": 18},
            {
                "oldest": datetime.datetime(2026, 4, 1, 8, 0, 0),
                "newest": datetime.datetime(2026, 4, 5, 10, 0, 0),
            },
            {
                "synced_profiles": 14,
                "active_profiles_7d": 9,
                "profiles_with_recent_reads": 8,
                "profiles_following_topics": 7,
                "profiles_following_sources": 6,
            },
            {
                "delivery_active": 5,
                "delivery_targets": 4,
                "morning_briefings": 4,
                "weekly_digests": 2,
                "breaking_topic_alerts": 3,
                "breaking_source_alerts": 1,
            },
            {
                "sends_7d": 12,
                "opens_7d": 8,
                "clicks_7d": 3,
            },
        ]
        mock_db.execute.side_effect = [
            [{"source": "MIA", "n": 50}],
            [{"category": "Политика", "n": 40}],
            [{"t": datetime.datetime(2026, 4, 5, 9, 0, 0), "n": 12}],
            [{"source": "MIA", "first_count": 6}],
            [{"topic": "Политика", "followers": 5}],
            [{"source": "MIA", "followers": 4}],
        ]

        with patch("routes.api.db", mock_db), \
             patch("routes.api.cached_response", return_value=None), \
             patch("routes.api.set_cache"):
            resp = client.get("/api/stats/full")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["editor_analytics"]["synced_profiles"] == 14
        assert data["editor_analytics"]["delivery_active"] == 5
        assert data["editor_analytics"]["open_rate_7d"] == 66.7
        assert data["editor_analytics"]["top_followed_topics"][0]["topic"] == "Политика"
        assert data["editor_analytics"]["top_followed_sources"][0]["source"] == "MIA"

    def test_delivery_track_redirects_and_records_event(self, client):
        mock_db = MagicMock()
        mock_db.execute_one.return_value = {
            "sync_token": "sync-token-123",
            "delivery_kind": "morning",
            "channel": "ntfy",
            "target": "reader-feed",
            "cluster_id": "abc123",
            "metadata": {},
        }

        with patch("routes.api.db", mock_db):
            resp = client.get("/api/delivery/track/open?event_id=7&redirect=/briefing")

        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://presek.live/briefing"
        mock_db.execute.assert_called_once()


# ── Security headers ──────────────────────────────────────────────

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/about")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert resp.headers.get("Strict-Transport-Security") is not None
        assert resp.headers.get("Content-Security-Policy") is not None
