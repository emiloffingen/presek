import importlib
import asyncio
import os
import sys
import types
from unittest.mock import patch, MagicMock, mock_open

class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _FakeFastAPI:
    def __init__(self, *args, **kwargs):
        self.user_middleware = []
        self.http_middlewares = []

    def add_middleware(self, cls, **options):
        self.user_middleware.append(types.SimpleNamespace(cls=cls, options=options))

    def middleware(self, _kind):
        def decorator(fn):
            self.http_middlewares.append(fn)
            return fn
        return decorator

    def get(self, _path, **_kwargs):
        def decorator(fn):
            return fn
        return decorator

    def post(self, _path, **_kwargs):
        def decorator(fn):
            return fn
        return decorator


class _FakeRequest:
    def __init__(self, payload, headers=None, client_host="127.0.0.1"):
        self._payload = payload
        self.headers = headers or {}
        self.client = types.SimpleNamespace(host=client_host)

    async def json(self):
        return self._payload


class _FakeRedirectResponse:
    def __init__(self, url, status_code=302):
        self.url = url
        self.status_code = status_code


class _FakeResponse:
    def __init__(self, content=None, media_type=None, headers=None, status_code=200):
        self.content = content
        self.media_type = media_type
        self.headers = headers or {}
        self.status_code = status_code


class _FakeJSONResponse(_FakeResponse):
    def __init__(self, status_code=200, content=None):
        super().__init__(content=content, media_type="application/json", status_code=status_code)


class _FakeFileResponse(_FakeResponse):
    def __init__(self, path, media_type=None, status_code=200):
        super().__init__(content=None, media_type=media_type, status_code=status_code)
        self.path = path


def _install_fake_fastapi_modules():
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.FastAPI = _FakeFastAPI
    fastapi_mod.Request = _FakeRequest
    fastapi_mod.Query = lambda default=None, **_kwargs: default
    fastapi_mod.HTTPException = _FakeHTTPException

    responses_mod = types.ModuleType("fastapi.responses")
    responses_mod.StreamingResponse = type("StreamingResponse", (), {})
    responses_mod.JSONResponse = _FakeJSONResponse
    responses_mod.RedirectResponse = _FakeRedirectResponse
    responses_mod.Response = _FakeResponse
    responses_mod.FileResponse = _FakeFileResponse

    cors_mod = types.ModuleType("fastapi.middleware.cors")
    cors_mod.CORSMiddleware = type("CORSMiddleware", (), {})
    gzip_mod = types.ModuleType("fastapi.middleware.gzip")
    gzip_mod.GZipMiddleware = type("GZipMiddleware", (), {})

    middleware_pkg = types.ModuleType("fastapi.middleware")

    return {
        "fastapi": fastapi_mod,
        "fastapi.responses": responses_mod,
        "fastapi.middleware": middleware_pkg,
        "fastapi.middleware.cors": cors_mod,
        "fastapi.middleware.gzip": gzip_mod,
    }


def _load_api_fast():
    sys.modules.pop("api_fast", None)
    fake_modules = _install_fake_fastapi_modules()
    with patch.dict(sys.modules, fake_modules):
        return importlib.import_module("api_fast")


def test_fastapi_cluster_ask_falls_back_when_local_and_ai_fail():
    with patch.dict(os.environ, {}, clear=False):
        api_fast = _load_api_fast()

    mock_db = MagicMock()
    mock_db.execute.return_value = [
        {"title": "T1", "description": "D1", "source": "MIA", "link": "https://example.com/1", "created_at": None, "category": "Свет"},
        {"title": "T2", "description": "D2", "source": "Reuters", "link": "https://example.com/2", "created_at": None, "category": "Свет"},
    ]
    mock_db.execute_one.return_value = None

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "answer_cluster_question_locally", side_effect=RuntimeError("boom")), \
         patch.object(api_fast, "_call_ai_async", side_effect=RuntimeError("boom")):
        data = asyncio.run(api_fast.ask_cluster("abc123def456", _FakeRequest({"question": "Што е ново?"})))

    assert data["status"] == "success"
    assert data["answer"]
    assert data["generated_locally"] is True
    assert data["confidence"] in {"low", "medium", "high"}
    assert data["citations"]


def test_fastapi_cluster_ask_falls_back_when_ai_response_is_invalid():
    with patch.dict(os.environ, {}, clear=False):
        api_fast = _load_api_fast()

    mock_db = MagicMock()
    mock_db.execute.return_value = [
        {"title": "T1", "description": "D1", "source": "MIA", "link": "https://example.com/1", "created_at": None, "category": "Свет"},
        {"title": "T2", "description": "D2", "source": "Reuters", "link": "https://example.com/2", "created_at": None, "category": "Свет"},
    ]
    mock_db.execute_one.return_value = None

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "answer_cluster_question_locally", return_value=None), \
         patch.object(api_fast, "_call_ai_async", return_value=('{"bad":', "test-provider")), \
         patch.object(api_fast, "clean_json_response", side_effect=ValueError("bad json")):
        data = asyncio.run(api_fast.ask_cluster("abc123def456", _FakeRequest({"question": "Што е ново?"})))

    assert data["status"] == "success"
    assert data["generated_locally"] is True


def test_fastapi_cluster_ask_falls_back_when_citation_ranking_blows_up():
    with patch.dict(os.environ, {}, clear=False):
        api_fast = _load_api_fast()

    mock_db = MagicMock()
    mock_db.execute.return_value = [
        {"title": "T1", "description": "D1", "source": "MIA", "link": "https://example.com/1", "created_at": None, "category": "Свет"},
        {"title": "T2", "description": "D2", "source": "Reuters", "link": "https://example.com/2", "created_at": None, "category": "Свет"},
    ]
    mock_db.execute_one.return_value = None

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "answer_cluster_question_locally", return_value={
             "answer": "Локален одговор",
             "related_questions": ["Следно?"],
             "confidence": "medium",
         }), \
         patch.object(api_fast, "_rank_cluster_citations", side_effect=RuntimeError("rank failed")):
        data = asyncio.run(api_fast.ask_cluster("abc123def456", _FakeRequest({"question": "Што е ново?"})))

    assert data["status"] == "success"
    assert data["answer"] == "Локален одговор"
    assert len(data["citations"]) == 2


def test_fastapi_cors_origins_follow_env_var():
    with patch.dict(os.environ, {"CORS_ORIGINS": "https://app.example, https://admin.example"}, clear=False):
        api_fast = _load_api_fast()

    cors = next(m for m in api_fast.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors.options["allow_origins"] == ["https://app.example", "https://admin.example"]


def test_fastapi_adds_gzip_middleware():
    api_fast = _load_api_fast()
    gzip = next(m for m in api_fast.app.user_middleware if m.cls.__name__ == "GZipMiddleware")
    assert gzip.options["minimum_size"] == 500


def test_fastapi_requires_critical_env_vars_at_import():
    sys.modules.pop("api_fast", None)
    fake_modules = _install_fake_fastapi_modules()
    with patch.dict(os.environ, {"DATABASE_URL": "", "SECRET_KEY": ""}, clear=False), \
         patch.dict(sys.modules, fake_modules):
        try:
            importlib.import_module("api_fast")
            assert False, "Expected import to fail without required env vars"
        except RuntimeError as exc:
            assert "Missing required environment variables" in str(exc)
            assert "DATABASE_URL" in str(exc)
            assert "SECRET_KEY" in str(exc)


def test_fastapi_rate_limit_path_helper_matches_expensive_routes():
    api_fast = _load_api_fast()
    assert api_fast._is_rate_limited_path("/api/chat_cluster") is True
    assert api_fast._is_rate_limited_path("/api/chat/stream") is True
    assert api_fast._is_rate_limited_path("/api/cluster/abc123def456/ask") is True
    assert api_fast._is_rate_limited_path("/api/news") is False


def test_fastapi_security_headers_helper_sets_expected_headers():
    api_fast = _load_api_fast()
    response = _FakeResponse(headers={})
    updated = api_fast._apply_security_headers(response)

    assert updated.headers["X-Content-Type-Options"] == "nosniff"
    assert updated.headers["X-Frame-Options"] == "DENY"
    assert updated.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in updated.headers["Content-Security-Policy"]


def test_fastapi_profile_sync_init_creates_token():
    api_fast = _load_api_fast()
    mock_db = MagicMock()

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast.secrets, "token_urlsafe", return_value="sync-token-123"):
        data = asyncio.run(api_fast.init_profile_sync())

    assert data["status"] == "success"
    assert data["token"] == "sync-token-123"
    assert data["profile"]["followedTopics"] == []
    mock_db.execute.assert_called_once()


def test_fastapi_profile_sync_get_returns_normalized_profile():
    api_fast = _load_api_fast()
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

    with patch.object(api_fast, "db", mock_db):
        data = asyncio.run(api_fast.get_profile_sync("sync-token-123"))

    assert data["status"] == "success"
    assert data["profile"]["followedTopics"] == ["Политика"]
    assert data["profile"]["deliveryPreferences"]["morningBriefing"] is False


def test_fastapi_profile_sync_save_merges_remote_and_local():
    api_fast = _load_api_fast()
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

    with patch.object(api_fast, "db", mock_db):
        data = asyncio.run(api_fast.save_profile_sync(_FakeRequest(payload)))

    assert data["status"] == "success"
    assert data["profile"]["followedTopics"] == ["Политика", "Економија"]
    assert data["profile"]["followedSources"] == ["Телма"]
    assert data["profile"]["recentClusters"][0]["cluster_id"] == "xyz"
    mock_db.execute.assert_called_once()


def test_fastapi_profile_delivery_get_returns_subscription():
    api_fast = _load_api_fast()
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

    with patch.object(api_fast, "db", mock_db):
        data = asyncio.run(api_fast.get_profile_delivery("sync-token-123"))

    assert data["status"] == "success"
    assert data["subscription"]["target"] == "reader-feed"
    assert data["subscription"]["weeklyDigest"] is True
    assert data["subscription"]["breakingTopics"] is True


def test_fastapi_profile_delivery_save_upserts_subscription():
    api_fast = _load_api_fast()
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

    with patch.object(api_fast, "db", mock_db):
        data = asyncio.run(api_fast.save_profile_delivery(_FakeRequest(payload)))

    assert data["status"] == "success"
    assert data["subscription"]["target"] == "reader-feed"
    assert data["subscription"]["weeklyDigest"] is True
    assert data["subscription"]["breakingSources"] is True
    mock_db.execute.assert_called_once()


def test_fastapi_stats_full_includes_editor_analytics():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute_one.side_effect = [
        {"count": 1200},
        {"count": 180},
        {"count": 600},
        {"count": 90},
        {"mb": 256.4},
        {"n": 18},
        {
            "oldest": __import__("datetime").datetime(2026, 4, 1, 8, 0, 0),
            "newest": __import__("datetime").datetime(2026, 4, 5, 10, 0, 0),
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
        [{"t": __import__("datetime").datetime(2026, 4, 5, 9, 0, 0), "n": 12}],
        [{"source": "MIA", "first_count": 6}],
        [{"topic": "Политика", "followers": 5}],
        [{"source": "MIA", "followers": 4}],
        [
            {"delivery_kind": "breaking", "sends": 10, "opens": 7, "clicks": 3},
            {"delivery_kind": "morning", "sends": 20, "opens": 10, "clicks": 2},
        ],
        [
            {"surface": "cluster", "impressions": 20, "follows": 5, "dismissals": 1, "topic_follows": 3, "source_follows": 2},
            {"surface": "settings", "impressions": 10, "follows": 1, "dismissals": 0, "topic_follows": 1, "source_follows": 0},
        ],
        [
            {"suggestion_kind": "topic", "impressions": 18, "follows": 5, "dismissals": 1},
            {"suggestion_kind": "source", "impressions": 12, "follows": 1, "dismissals": 0},
        ],
        [
            {"surface": "cluster", "current_impressions": 8, "current_follows": 3, "previous_impressions": 10, "previous_follows": 2},
            {"surface": "settings", "current_impressions": 4, "current_follows": 0, "previous_impressions": 4, "previous_follows": 1},
        ],
    ]

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "cached_response", return_value=None), \
         patch.object(api_fast, "set_cache"):
        data = asyncio.run(api_fast.get_stats_full())

    assert data["editor_analytics"]["synced_profiles"] == 14
    assert data["editor_analytics"]["delivery_active"] == 5
    assert data["editor_analytics"]["open_rate_7d"] == 66.7
    assert data["editor_analytics"]["top_followed_topics"][0]["topic"] == "Политика"
    assert data["editor_analytics"]["top_followed_sources"][0]["source"] == "MIA"
    assert data["editor_analytics"]["delivery_kind_performance"][0]["delivery_kind"] == "breaking"
    assert data["editor_analytics"]["delivery_kind_performance"][0]["click_rate"] == 30.0
    assert data["editor_analytics"]["suggestion_surface_performance"][0]["surface"] == "cluster"
    assert data["editor_analytics"]["suggestion_surface_performance"][0]["trend_label"] == "Во раст"
    assert data["editor_analytics"]["suggestion_surface_performance"][0]["current_7d_rate"] == 37.5
    assert data["editor_analytics"]["suggestion_kind_performance"][0]["suggestion_kind"] == "topic"


def test_fastapi_suggestion_event_save_records_rows():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute_one.return_value = {"exists": 1}
    payload = {
        "token": "sync-token-123",
        "clientId": "reader_abc123",
        "events": [
            {
                "surface": "cluster",
                "eventType": "impression",
                "suggestionKind": "topic",
                "value": "Политика",
            },
            {
                "surface": "cluster",
                "eventType": "follow",
                "suggestionKind": "topic",
                "value": "Политика",
            },
        ],
    }

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "delete_cache"):
        data = asyncio.run(api_fast.save_suggestion_events(_FakeRequest(payload)))

    assert data["status"] == "success"
    assert data["accepted"] == 2
    assert mock_db.execute.call_count == 2


def test_fastapi_delivery_track_records_event_and_redirects():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute_one.return_value = {
        "sync_token": "sync-token-123",
        "delivery_kind": "morning",
        "channel": "ntfy",
        "target": "reader-feed",
        "cluster_id": "abc123",
        "metadata": {},
    }

    with patch.object(api_fast, "db", mock_db):
        response = asyncio.run(api_fast.track_delivery_event("open", 7, "/briefing"))

    assert response.status_code == 302
    assert response.url.endswith("/briefing")
    mock_db.execute.assert_called_once()


def test_fastapi_international_curated_returns_ranked_clusters():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        [
            {"cluster_id": "aaa111", "title": "Прва меѓународна приказна со преведен наслов", "description": "D1", "source": "Reuters"},
            {"cluster_id": "bbb222", "title": "Втора светска приказна со јасен македонски наслов", "description": "D2", "source": "BBC"},
        ],
        [{"cluster_id": "aaa111", "representative_image": "https://img/1.webp"}],
    ]
    mock_db.get_synthesis_ids.return_value = ["aaa111"]

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "cached_response", return_value=None), \
         patch.object(api_fast, "rank_articles_in_cluster", side_effect=lambda arts: arts), \
         patch.object(api_fast, "score_cluster", side_effect=lambda arts: 2 if arts[0]["cluster_id"] == "aaa111" else 1), \
         patch.object(api_fast, "calculate_reading_time", return_value=1), \
         patch.object(api_fast, "set_cache"):
        data = asyncio.run(api_fast.get_international_curated(limit=2))

    assert data["status"] == "success"
    assert len(data["clusters"]) == 2
    assert data["clusters"][0]["cluster_id"] == "aaa111"
    assert data["clusters"][0]["has_synthesis"] is True


def test_fastapi_international_curated_filters_non_macedonian_titles():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        [
            {
                "cluster_id": "bad111",
                "title": "Potresna objava u Денес Showu: Imam Parkinsonovu bolest.",
                "description": "Mixed language",
                "source": "Jutarnji",
            },
            {
                "cluster_id": "good222",
                "title": "Алкохолизмот во литературата: Кога нивото на алкохолот во крвта се намалува",
                "description": "Translated",
                "source": "FAZ",
            },
        ],
        [{"cluster_id": "good222", "representative_image": "https://img/2.webp"}],
    ]
    mock_db.get_synthesis_ids.return_value = []

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "cached_response", return_value=None), \
         patch.object(api_fast, "rank_articles_in_cluster", side_effect=lambda arts: arts), \
         patch.object(api_fast, "score_cluster", return_value=1), \
         patch.object(api_fast, "calculate_reading_time", return_value=1), \
         patch.object(api_fast, "set_cache"):
        data = asyncio.run(api_fast.get_international_curated(limit=4))

    assert data["status"] == "success"
    assert [cluster["cluster_id"] for cluster in data["clusters"]] == ["good222"]


def test_fastapi_chat_cluster_reuses_cluster_answer_payload():
    api_fast = _load_api_fast()

    with patch.object(api_fast, "_build_cluster_answer_payload", return_value={
        "status": "success",
        "answer": "Одговор",
        "citations": [],
        "related_questions": [],
        "confidence": "medium",
        "confirmed_points": [],
        "unclear_points": [],
        "source_differences": "",
    }):
        data = asyncio.run(api_fast.chat_cluster(_FakeRequest({"cluster_id": "abc123def456", "query": "Што е ново?"})))

    assert data["status"] == "success"
    assert data["answer"] == "Одговор"
    assert data["response"] == "Одговор"


def test_fastapi_source_control_updates_source_for_local_admin():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute_one.side_effect = [
        {"name": "MIA", "credibility": 1.0},
        {"name": "MIA", "credibility": 1.2, "is_active": True},
    ]

    with patch.object(api_fast, "db", mock_db), \
         patch.object(api_fast, "get_source_statuses", return_value={"MIA": {"quality_label": "Стабилен извор"}}):
        data = asyncio.run(
            api_fast.control_source(
                "MIA",
                _FakeRequest({"action": "uprank"}, client_host="127.0.0.1"),
            )
        )

    assert data["status"] == "success"
    assert data["source"]["source_status"]["quality_label"] == "Стабилен извор"
    mock_db.execute.assert_called_once()


def test_fastapi_get_sources_includes_paused_sources():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        [
            {"name": "MIA", "country": "🇲🇰", "category": "Главни", "credibility": 1.5, "is_active": True, "pause_mode": None, "pause_reason": None, "paused_at": None, "last_fetched": None},
            {"name": "Paused Feed", "country": "🇲🇰", "category": "Независни", "credibility": 0.8, "is_active": False, "pause_mode": "manual", "pause_reason": "Manual pause", "paused_at": "2026-04-06T00:00:00+00:00", "last_fetched": None},
        ],
        [{"source": "MIA", "count": 5}],
        [{"source": "MIA", "first_count": 2}],
        [{"source": "MIA", "lead_count_30d": 3, "corroborated_lead_count_30d": 2, "solo_lead_count_30d": 1, "recent_7d_volume": 4, "previous_7d_volume": 2}],
    ]

    with patch.object(api_fast, "db", mock_db):
        data = asyncio.run(api_fast.get_sources())

    assert len(data) == 2
    assert any(row["source"] == "Paused Feed" and row["is_active"] is False for row in data)
    first_query = mock_db.execute.call_args_list[0].args[0]
    assert "FROM sources ORDER BY is_active DESC, name ASC" in first_query


def test_fastapi_proxy_serves_local_static_files():
    api_fast = _load_api_fast()

    with patch.object(api_fast.os.path, "exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=b"svg-bytes")):
        response = asyncio.run(api_fast.proxy_image("/static/example.svg", None))

    assert response.status_code == 200
    assert response.media_type == "image/svg+xml"
    assert response.content == b"svg-bytes"


def test_fastapi_serves_sw_and_manifest_as_files():
    api_fast = _load_api_fast()

    sw = asyncio.run(api_fast.serve_sw())
    manifest = asyncio.run(api_fast.serve_manifest())

    assert sw.path == "sw.js"
    assert sw.media_type == "application/javascript"
    assert manifest.path.endswith("static/manifest.json")


def test_fastapi_serves_static_assets_from_static_root():
    api_fast = _load_api_fast()
    response = asyncio.run(api_fast.serve_static_asset("manifest.json"))
    assert str(response.path).endswith("static/manifest.json")


def test_fastapi_serves_robots_txt():
    api_fast = _load_api_fast()
    response = asyncio.run(api_fast.robots_txt())
    assert response.media_type == "text/plain"
    assert "User-agent" in response.content


def test_fastapi_serves_og_cluster_svg():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute_one.side_effect = [
        {"title": "Наслов"},
        {"count": 3},
    ]
    with patch.object(api_fast, "db", mock_db):
        response = asyncio.run(api_fast.og_cluster_image("abc123def456"))
    assert response.media_type == "image/svg+xml"
    assert "Наслов" in response.content
    assert "3 извори" in response.content


def test_fastapi_serves_default_og_image():
    api_fast = _load_api_fast()
    mock_db = MagicMock()
    mock_db.execute_one.return_value = {"count": 42}
    with patch.object(api_fast, "db", mock_db):
        response = asyncio.run(api_fast.og_image())
    assert response.media_type == "image/svg+xml"
    assert "42 статии индексирани" in response.content
