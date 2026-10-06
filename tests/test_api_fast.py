import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Robust Global FastAPI Mocks ---


from fastapi import HTTPException as _FakeHTTPException


class _FakeFastAPI:
    def __init__(self, *args, **kwargs):
        self.user_middleware = []
        self.http_middlewares = []
        self.state = types.SimpleNamespace()

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

    def api_route(self, _path, **_kwargs):
        def decorator(fn):
            return fn

        return decorator

    def include_router(self, router, **kwargs):
        pass

    def mount(self, _path, _app, **_kwargs):
        pass

    def on_event(self, _name):
        def decorator(fn):
            return fn

        return decorator

    def exception_handler(self, _exc):
        def decorator(fn):
            return fn

        return decorator


class _FakeRequest:
    def __init__(self, payload=None, headers=None, client_host="127.0.0.1"):
        self._payload = payload or {}

        class _CIHeaders(dict):
            def get(self, key, default=None):
                return super().get(str(key).lower(), default)

        self.headers = _CIHeaders({k.lower(): v for k, v in (headers or {}).items()})
        self.client = types.SimpleNamespace(host=client_host)
        self.url = types.SimpleNamespace(path="/", path_params={})
        self.cookies = {}

    async def json(self):
        return self._payload


class _FakeResponse:
    def __init__(self, content=None, media_type=None, headers=None, status_code=200):
        self.content = content
        self.media_type = media_type
        self.headers = headers or {}
        self.status_code = status_code

    def __getitem__(self, key):
        if isinstance(self.content, dict):
            return self.content[key]
        raise KeyError(key)

    def get(self, key, default=None):
        return self.content.get(key, default) if isinstance(self.content, dict) else default


class _FakeJSONResponse(_FakeResponse):
    def __init__(self, status_code=200, content=None, headers=None):
        super().__init__(content, "application/json", headers or {}, status_code)


def _get_fake_fastapi_modules():
    import importlib.machinery

    def make_mod(name):
        m = types.ModuleType(name)
        m.__spec__ = importlib.machinery.ModuleSpec(name, None)
        return m

    f = make_mod("fastapi")
    f.FastAPI = _FakeFastAPI

    class _FakeRouter:
        def get(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def post(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def include_router(self, *args, **kwargs):
            pass

    f.APIRouter = _FakeRouter
    f.Request = _FakeRequest
    f.HTTPException = _FakeHTTPException
    f.Query = MagicMock(side_effect=lambda default=None, **kwargs: default)
    f.Path = MagicMock(side_effect=lambda default=None, **kwargs: default)
    f.BackgroundTasks = MagicMock
    f.Depends = MagicMock
    f.Form = MagicMock
    f.Header = MagicMock

    r = make_mod("fastapi.responses")
    r.JSONResponse = _FakeJSONResponse
    r.HTMLResponse = MagicMock
    r.RedirectResponse = MagicMock
    r.FileResponse = MagicMock
    r.StreamingResponse = MagicMock
    r.Response = _FakeResponse

    mc = make_mod("fastapi.middleware.cors")
    mc.CORSMiddleware = MagicMock

    mg = make_mod("fastapi.middleware.gzip")
    mg.GZipMiddleware = MagicMock

    m = make_mod("fastapi.middleware")
    sf = make_mod("fastapi.staticfiles")
    sf.StaticFiles = MagicMock
    sec = make_mod("fastapi.security")

    class _FakeHTTPBearer:
        def __init__(self, auto_error=True):
            self.auto_error = auto_error

        async def __call__(self, request):
            return None

    sec.HTTPAuthorizationCredentials = MagicMock
    sec.HTTPBearer = _FakeHTTPBearer

    return {
        "fastapi": f,
        "fastapi.responses": r,
        "fastapi.middleware": m,
        "fastapi.middleware.cors": mc,
        "fastapi.middleware.gzip": mg,
        "fastapi.staticfiles": sf,
        "fastapi.security": sec,
    }


@pytest.fixture(scope="module", autouse=True)
def _install_fake_fastapi_modules():
    original_modules = {name: sys.modules.get(name) for name in _get_fake_fastapi_modules()}
    sys.modules.update(_get_fake_fastapi_modules())
    for name in [
        "api_fast",
        "core.api_fast",
        "routes",
        "routes.home",
        "routes.news",
        "routes.profile",
        "routes.stats",
        "routes.system",
        "routes.intelligence",
        "routes.security",
    ]:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        for name in [
            "api_fast",
            "core.api_fast",
            "routes",
            "routes.home",
            "routes.news",
            "routes.profile",
            "routes.stats",
            "routes.system",
            "routes.intelligence",
            "routes.security",
        ]:
            sys.modules.pop(name, None)


@pytest.fixture
def mock_all():
    m_db = MagicMock()
    m_db.async_execute = AsyncMock(return_value=[])
    m_db.async_execute_one = AsyncMock(return_value={})
    m_db.async_get_synthesis_ids = AsyncMock(return_value=[])
    m_db.async_search_articles = AsyncMock(return_value=[])
    m_db.async_hybrid_search = AsyncMock(return_value=[])
    m_ai = AsyncMock(return_value=('{"answer":"ok"}', "prov"))

    # Patch everything - use importlib to patch database module
    with (
        patch.dict("sys.modules", {"database": MagicMock(db_manager=m_db)}),
        patch("core.database.db_manager", m_db),
        patch("core.ai_engine._call_ai_async", m_ai),
    ):
        m_db.hybrid_search.return_value = []
        yield {"db": m_db, "ai": m_ai}


def test_fastapi_news_scales_query_fetch_limit_with_page_depth(mock_all):
    import routes.news as news_routes

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("core.embeddings.generate_query_embedding", return_value=None),
    ):
        asyncio.run(news_routes.get_news(q="Ekonomija", page=3, page_size=25))
    assert mock_all["db"].async_search_articles.called
    assert mock_all["db"].async_search_articles.call_args.kwargs["limit"] == 500


def test_fastapi_news_search_falls_back_to_text_search_when_hybrid_fails(mock_all):
    import routes.news as news_routes

    mock_all["db"].async_hybrid_search.side_effect = RuntimeError("canceling statement due to statement timeout")
    mock_all["db"].async_search_articles.return_value = []

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("core.embeddings.get_query_embedding_async", new=AsyncMock(return_value=[0.1] * 384)),
    ):
        data = asyncio.run(news_routes.get_news(q="Bugarija", page=0, page_size=10))
        data = data.content if hasattr(data, "content") else data

    assert mock_all["db"].async_hybrid_search.called
    assert mock_all["db"].async_hybrid_search.call_args.kwargs["timeout_ms"] == news_routes._SEARCH_SEMANTIC_TIMEOUT_MS
    assert mock_all["db"].async_search_articles.called  # fell back instead of failing
    assert data["status"] == "success"


def test_fastapi_news_search_uses_hybrid_results_without_fallback(mock_all):
    import routes.news as news_routes

    mock_all["db"].async_hybrid_search.return_value = []

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("core.embeddings.get_query_embedding_async", new=AsyncMock(return_value=[0.1] * 384)),
    ):
        asyncio.run(news_routes.get_news(q="Bugarija", page=0, page_size=10))

    assert mock_all["db"].async_hybrid_search.called
    assert not mock_all["db"].async_search_articles.called


def test_fastapi_profile_sync_init_creates_token(mock_all):
    import routes.profile as profile_routes

    with patch("secrets.token_urlsafe", return_value="token123"):
        with pytest.raises(Exception) as exc:
            asyncio.run(profile_routes.init_profile_sync())
    assert exc.value.status_code == 400


def test_fastapi_profile_sync_init_creates_strong_token(mock_all):
    import routes.profile as profile_routes

    strong_token = "A_valid_sync_token_value_12345"
    with patch("secrets.token_urlsafe", return_value=strong_token):
        data = asyncio.run(profile_routes.init_profile_sync())
    assert data["token"] == strong_token
    mock_all["db"].async_execute.assert_called()


def test_client_ip_only_trusts_configured_proxies(mock_all):
    import routes.common as common

    spoofed = _FakeRequest(
        headers={"x-forwarded-for": "8.8.8.8"},
        client_host="172.18.0.9",
    )
    assert common._client_ip_for_request(spoofed) == "172.18.0.9"

    with patch.dict(os.environ, {"TRUSTED_PROXY_CIDRS": "172.18.0.0/16"}, clear=False):
        trusted = _FakeRequest(
            headers={"x-forwarded-for": "8.8.8.8"},
            client_host="172.18.0.9",
        )
        assert common._client_ip_for_request(trusted) == "8.8.8.8"


def test_rate_limited_paths_include_public_ai_endpoints(mock_all):
    import routes.common as common

    assert common._is_rate_limited_path("/api/intelligence/cluster/abc123/research") is True
    assert common._is_rate_limited_path("/api/intelligence/cluster/abc123/analyst") is True
    assert common._is_rate_limited_path("/api/profile/sync/personalized-news") is True
    assert common._is_rate_limited_path("/api/news") is True
    assert common._is_rate_limited_path("/api/v1/news") is True
    assert common._is_rate_limited_path("/api/proxy") is True
    assert common._is_rate_limited_path("/api/health") is False


def test_profile_sync_rejects_weak_token_headers(mock_all):
    import routes.profile as profile

    with pytest.raises(Exception) as exc:
        asyncio.run(profile.get_profile_sync(_FakeRequest(headers={"x-sync-token": "short-token"})))
    assert exc.value.status_code == 400


def test_profile_sync_rejects_invalid_body_token(mock_all):
    import routes.profile as profile

    with pytest.raises(Exception) as exc:
        asyncio.run(profile.save_profile_sync(_FakeRequest(payload={"token": "bad token with spaces", "profile": {}})))
    assert exc.value.status_code == 400


def test_fastapi_public_health_omits_internal_connection_details(mock_all):
    import routes.system as system_routes

    with (
        patch(
            "routes.system._probe_database",
            return_value={"ok": True, "article_count": 8},
        ),
        patch("routes.system._probe_redis", return_value={"ok": False, "url": "secret"}),
    ):
        data = asyncio.run(system_routes.health(_FakeRequest()))
    assert "url" not in data["redis"]
    from core.version import APP_VERSION, APP_VERSION_LABEL

    assert data["version"] == APP_VERSION
    assert data["version_label"] == APP_VERSION_LABEL
    assert isinstance(data["uptime_seconds"], int)


def test_fastapi_only_registers_prefixed_routers(mock_all):
    content = open(os.path.join(os.path.dirname(__file__), "..", "core", "api_fast.py"), encoding="utf-8").read()
    assert 'app.include_router(news.router, prefix="/api")' in content
    assert 'app.include_router(home.router, prefix="/api")' in content
    assert "app.include_router(news.router)\n" not in content


def _with_homepage_synthesis(cluster, *, homepage_score=5.0):
    enriched = dict(cluster)
    enriched["homepage_score"] = homepage_score
    return enriched


def test_home_live_now_route_uses_backend_selection(mock_all):
    import routes.home as home

    recent_payload = {
        "status": "success",
        "clusters": [
            {
                "cluster_id": "excluded",
                "live_now_fit": True,
                "live_now_score": 9.0,
                "articles": [
                    {
                        "title": "Excluded",
                        "source": "MIA",
                        "created_at": "2026-04-22T18:20:00Z",
                    }
                ],
            },
            {
                "cluster_id": "live-1",
                "live_now_fit": True,
                "live_now_score": 8.0,
                "articles": [
                    {
                        "title": "Live 1",
                        "source": "Kanal 5",
                        "created_at": "2026-04-22T18:15:00Z",
                    }
                ],
            },
            {
                "cluster_id": "live-2",
                "live_now_fit": True,
                "live_now_score": 7.5,
                "articles": [
                    {
                        "title": "Live 2",
                        "source": "Alsat",
                        "created_at": "2026-04-22T18:12:00Z",
                    }
                ],
            },
            {
                "cluster_id": "junk",
                "live_now_fit": False,
                "live_now_score": 10.0,
                "articles": [
                    {
                        "title": "Junk",
                        "source": "Expres",
                        "created_at": "2026-04-22T18:25:00Z",
                    }
                ],
            },
        ],
    }

    with patch("routes.home.fetch_news_data", new=AsyncMock(return_value=recent_payload)):
        data = asyncio.run(home.get_home_live_now(exclude="excluded"))

    assert data["status"] == "success"
    assert [item["cluster_id"] for item in data["clusters"]] == ["live-1", "live-2"]


def test_home_latest_wire_route_uses_backend_selection(mock_all):
    import routes.home as home

    recent_payload = {
        "status": "success",
        "clusters": [
            {
                "cluster_id": "wire-1",
                "articles": [
                    {
                        "title": "Teska soobracajka na ekspresniot pat kaj Rankovce",
                        "source": "Press24",
                        "topic": "Kriminal",
                        "category": "Srbija",
                        "created_at": "2026-04-22T18:12:00Z",
                        "link": "https://wire-1",
                    }
                ],
            },
            {
                "cluster_id": "junk-1",
                "articles": [
                    {
                        "title": "Izdanie na 360°: intervju so ministerot",
                        "source": "360",
                        "topic": "Politika",
                        "category": "Srbija",
                        "created_at": "2026-04-22T18:11:00Z",
                        "link": "https://junk-1",
                    }
                ],
            },
            {
                "cluster_id": "wire-2",
                "articles": [
                    {
                        "title": "Sobranieto otvori rasprava za budzetot",
                        "source": "Kanal 5",
                        "topic": "Ekonomija",
                        "category": "Srbija",
                        "created_at": "2026-04-22T18:10:00Z",
                        "link": "https://wire-2",
                    }
                ],
            },
            {
                "cluster_id": "wire-3",
                "articles": [
                    {
                        "title": "Postojano ste umorni, proverete dali vi nedostiga ovoj mineral",
                        "source": "Expres",
                        "topic": "Zdravje",
                        "category": "Srbija",
                        "created_at": "2026-04-22T18:13:00Z",
                        "link": "https://wire-3",
                    }
                ],
            },
        ],
    }

    with patch("routes.home.fetch_news_data", new=AsyncMock(return_value=recent_payload)):
        data = asyncio.run(home.get_home_latest_wire(limit=10))

    assert data["status"] == "success"
    assert [item["title"] for item in data["articles"]] == [
        "Teska soobracajka na ekspresniot pat kaj Rankovce",
        "Sobranieto otvori rasprava za budzetot",
    ]


def test_news_topic_response_filters_mixed_cluster_articles(mock_all):
    import routes.news as news

    async def execute_side_effect(query, params=None, fetch=True, **kwargs):
        if "WITH topic_clusters AS" in query:
            return [{"cluster_id": "mixed", "last_article": "2026-04-22T20:00:00Z"}]
        if "WHERE cluster_id = ANY" in query or "WHERE a.cluster_id = ANY" in query:
            return [
                {
                    "id": 1,
                    "cluster_id": "mixed",
                    "source": "Vecer",
                    "title": "Eks-fudbalerot na Celzi ce bide naslednikot na Rozenior?",
                    "description": "",
                    "topic": "vesti",
                    "category": "Srbija",
                    "created_at": "2026-04-22T20:00:00Z",
                },
                {
                    "id": 2,
                    "cluster_id": "mixed",
                    "source": "SportSport",
                    "title": "Eks-fudbalerot na Celzi ce bide naslednikot na Rozenior?",
                    "description": "",
                    "topic": "Sport",
                    "category": "Evropa",
                    "created_at": "2026-04-22T19:55:00Z",
                },
            ]
        if "SELECT cluster_id, representative_image, dominant_color FROM cluster_metadata" in query:
            return [
                {
                    "cluster_id": "mixed",
                    "representative_image": None,
                    "dominant_color": None,
                }
            ]
        if "FROM cluster_summaries" in query and "key_facts" in query:
            return []
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute.side_effect = execute_side_effect
    mock_all["db"].async_get_synthesis_ids.return_value = []

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache"),
        patch("routes.news.score_cluster", return_value=1.0),
        patch("routes.news.score_cluster_for_homepage", return_value=1.0),
    ):
        data = asyncio.run(news.get_news(topic="Sport", page_size=10))

    assert data["status"] == "success"
    assert len(data["clusters"]) == 1
    assert [article["topic"] for article in data["clusters"][0]["articles"]] == ["Sport"]
    assert data["clusters"][0]["articles"][0]["source"] == "SportSport"


def test_news_entity_response_merges_metadata_and_article_matches(mock_all):
    import routes.news as news

    async def execute_side_effect(query, params=None, fetch=True, **kwargs):
        if "WITH entity_clusters AS" in query:
            return [
                {
                    "cluster_id": "fresh-text-match",
                    "last_article": "2026-04-30T23:20:00Z",
                },
                {
                    "cluster_id": "old-entity-match",
                    "last_article": "2026-04-27T12:00:00Z",
                },
            ]
        if "FROM articles WHERE cluster_id = ANY" in query:
            return [
                {
                    "id": 1,
                    "cluster_id": "fresh-text-match",
                    "source": "MIA",
                    "title": "Iran isprati nov predlog",
                    "description": "novi detali za razgovorite.",
                    "summary": "Iran e del od aktuelniot predlog.",
                    "topic": "Svet",
                    "category": "Svet",
                    "created_at": "2026-04-30T23:20:00Z",
                    "ingested_at": "2026-04-30T23:21:00Z",
                },
                {
                    "id": 2,
                    "cluster_id": "old-entity-match",
                    "source": "Archive",
                    "title": "Postara vest za Iran",
                    "description": "",
                    "summary": "",
                    "topic": "Svet",
                    "category": "Svet",
                    "created_at": "2026-04-27T12:00:00Z",
                    "ingested_at": "2026-04-27T12:01:00Z",
                },
            ]
        if "SELECT cluster_id, representative_image, dominant_color FROM cluster_metadata" in query:
            return [
                {
                    "cluster_id": "fresh-text-match",
                    "representative_image": None,
                    "dominant_color": None,
                },
                {
                    "cluster_id": "old-entity-match",
                    "representative_image": None,
                    "dominant_color": None,
                },
            ]
        if "FROM cluster_summaries" in query and "key_facts" in query:
            return []
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute.side_effect = execute_side_effect
    mock_all["db"].async_get_synthesis_ids.return_value = []

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache"),
        patch("routes.news.score_cluster", return_value=1.0),
        patch("routes.news.score_cluster_for_homepage", return_value=1.0),
    ):
        data = asyncio.run(news.get_news(entity="Iran", page_size=10))

    assert data["status"] == "success"
    assert [cluster["cluster_id"] for cluster in data["clusters"]] == [
        "fresh-text-match",
        "old-entity-match",
    ]


def test_news_editorial_signals_classify_story_state(mock_all):
    import routes.news as news

    arts = [
        {
            "title": "Sobranieto otvori rasprava za budzetot",
            "source": "MIA",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T18:10:00Z",
        },
        {
            "title": "Telma: raspravata za budzetot prodolzuva",
            "source": "Telma",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T18:05:00Z",
        },
        {
            "title": "Kanal 5: novi detali od raspravata",
            "source": "Kanal 5",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T18:00:00Z",
        },
    ]

    signals = news._compute_editorial_signals(arts, cluster_score=2.5, homepage_score=2.0)

    assert signals["story_state"] in {"developing", "confirmed", "stale"}
    assert signals["live_now_fit"] in (True, False)
    assert signals["importance_score"] > 0
    assert signals["trust_score"] > 0


def test_fastapi_proxy_rejects_remote_svg_content(mock_all):
    import routes.system as system_routes

    fake_resp = MagicMock(status_code=200, headers={"Content-Type": "image/svg+xml"})
    with (
        patch("routes.system._resolve_public_ips", return_value=["1.2.3.4"]),
        patch("routes.system._peer_ip", return_value="1.2.3.4"),
        patch("requests.get", return_value=fake_resp),
    ):
        response = asyncio.run(system_routes.proxy_image("https://c.com/a.svg", None))
    assert response.status_code in {415, 200}


def test_fastapi_proxy_ignores_unsafe_db_local_image_path(mock_all):
    import routes.system as system_routes

    mock_all["db"].async_execute_one.return_value = {
        "local_image_path": "../../../etc/passwd",
    }

    with (
        patch("routes.system.generate_local_placeholder", return_value="<svg/>", create=True),
        patch("utils.network._resolve_public_ips", side_effect=ValueError("blocked")),
    ):
        response = asyncio.run(system_routes.proxy_image("https://example.com/image.jpg", None))

    assert response.media_type == "image/svg+xml"
    assert response.headers["X-Proxy-Fallback"] == "http_404"


def test_fastapi_proxy_serves_local_master_without_remote_fetch(mock_all, tmp_path):
    import io

    from PIL import Image

    import routes.system as system_routes

    master = tmp_path / "art_1.png"
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, "PNG")
    master.write_bytes(buf.getvalue())
    mock_all["db"].async_execute_one.return_value = {"local_image_path": "uploads/art_1.png"}

    with (
        patch("routes.system._resolve_safe_static_relative", return_value=master),
        patch("requests.get", side_effect=AssertionError("remote fetch must not happen")),
        patch("utils.network._resolve_public_ips", side_effect=AssertionError("remote fetch must not happen")),
    ):
        response = asyncio.run(system_routes.proxy_image("https://example.com/image.jpg", None))

    assert response.status_code == 200
    assert response.media_type in {"image/webp", "image/png", "image/jpeg"}
    assert response.headers.get("X-Proxy-Fallback") is None


def test_fastapi_serves_robots_txt(mock_all):
    import routes.system as system_routes

    resp = asyncio.run(system_routes.robots_txt())
    assert "User-agent" in resp.content


def test_fastapi_serves_get_cluster_share_card(mock_all):
    import routes.system as system_routes

    mock_all["db"].execute_one.side_effect = [{"title": "T"}, {"summary": "S"}]
    mock_all["db"].execute.return_value = [{"title": "T1", "source": "S1", "category": "C1"}]

    with (
        patch("PIL.Image.new"),
        patch("PIL.ImageDraw.Draw"),
        patch("PIL.ImageFont.truetype"),
    ):
        resp = asyncio.run(system_routes.get_cluster_share_card("abc123"))
        assert resp.media_type == "image/png"


def test_fastapi_get_cluster_share_card_blocks_unresolved_remote_backgrounds(mock_all):
    import routes.system as system_routes

    mock_all["db"].execute.return_value = [
        {
            "title": "T1",
            "source": "S1",
            "category": "C1",
            "image_url": "http://169.254.169.254/latest/meta-data",
            "local_image_path": None,
        }
    ]
    mock_all["db"].execute_one.side_effect = [
        {
            "representative_image": "http://169.254.169.254/latest/meta-data",
            "dominant_color": None,
        },
    ]

    fake_image = MagicMock()
    fake_client = MagicMock()

    with (
        patch("routes.system._resolve_public_ips", side_effect=ValueError("Blocked URL")),
        patch("httpx.Client", return_value=fake_client),
        patch("PIL.Image.new", return_value=fake_image),
        patch("PIL.ImageDraw.Draw"),
        patch("PIL.ImageFont.truetype"),
    ):
        fake_image.save.side_effect = lambda output, format=None: output.write(b"png")
        resp = asyncio.run(system_routes.get_cluster_share_card("abc123"))
    fake_client.get.assert_not_called()
    assert resp.media_type == "image/png"


def test_fastapi_historical_events_formats_pgvector_parameter(mock_all):
    import routes.news

    async def async_execute_side_effect(query, params=None, fetch=True, **kwargs):
        if "SELECT embedding FROM articles" in query:
            return [{"embedding": "[0.1,0.2,0.3]"}]
        if "WITH archive_pool AS" in query:
            assert isinstance(params[0], str)
            assert params[0].startswith("[") and params[0].endswith("]")
            return []
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute.side_effect = async_execute_side_effect

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache"),
    ):
        resp = asyncio.run(routes.news.get_historical_events("abc123"))
        data = resp.content if hasattr(resp, "content") else resp

    assert data["status"] == "success" and data["events"] == []


def test_request_size_middleware_rejects_large_content_length():
    from routes.security import MAX_REQUEST_BODY_SIZE, RequestSizeMiddleware

    request = types.SimpleNamespace(
        headers={"content-length": str(MAX_REQUEST_BODY_SIZE + 1)},
        query_params={},
    )
    middleware = RequestSizeMiddleware(app=MagicMock())

    with pytest.raises(Exception) as exc:
        asyncio.run(middleware.dispatch(request, AsyncMock()))

    assert exc.value.status_code == 413


def test_request_size_middleware_rejects_long_query_param():
    from routes.security import MAX_QUERY_PARAM_LENGTH, RequestSizeMiddleware

    request = types.SimpleNamespace(
        headers={},
        query_params={"q": "x" * (MAX_QUERY_PARAM_LENGTH + 1)},
    )
    middleware = RequestSizeMiddleware(app=MagicMock())

    with pytest.raises(Exception) as exc:
        asyncio.run(middleware.dispatch(request, AsyncMock()))

    assert exc.value.status_code == 400


def test_stats_summary_includes_intelligence_payload(mock_all):
    import routes.stats

    def execute_one_side_effect(query, *args, **kwargs):
        if "category IN" in query and ("is_global" in query or "Svet" in query):
            return {"count": 18}
        if "COUNT(*) FROM articles WHERE COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '1 hour'" in query:
            return {"count": 12}
        if "COUNT(*) FROM sources WHERE is_active = TRUE" in query:
            return {"count": 40}
        if "FROM cluster_summaries s" in query:
            return {
                "quote": "",
                "summary": "• Q\n• R",
                "generated_article": "",
                "cluster_id": "abc123",
                "title": "T",
            }
        if "SELECT COUNT(*) FROM articles" in query and "INTERVAL '24 hours'" in query:
            return {"count": 120}
        if "SELECT COUNT(*) FROM articles" in query:
            return {"count": 200}
        if "FROM cluster_tiers" in query:
            return {"total_clusters": 20, "high_consensus": 5, "diverse_sources": 8}
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute_one.side_effect = execute_one_side_effect

    with (
        patch("routes.stats.cached_response", return_value=None),
        patch("routes.stats.set_cache"),
        patch("routes.common.db", mock_all["db"]),
        patch.object(
            routes.stats.redis_client,
            "hgetall",
            return_value={
                "synthesis_path|mode=ai": "3",
                "synthesis_path|mode=local_fallback": "1",
            },
        ),
    ):
        data = asyncio.run(routes.stats.get_stats_summary())

    assert data["last_24h"] == 120
    assert data["quote_of_the_day"]["cluster_id"] == "abc123"
    assert data["quote_of_the_day"]["quote"] == "Q"
    assert data["intelligence"]["international_share_pct"] == 15.0
    assert data["intelligence"]["synthesis_transparency"]["systemic_ratio"] == 75.0
    assert data["intelligence"]["pluralism"]["pluralism_pct"] == 65.0
    assert data["intelligence"]["pluralism"]["high_consensus_pct"] == 25.0


def test_navigation_counts_use_article_level_classifications(mock_all):
    import routes.system as system

    async def execute_side_effect(query, params=None, fetch=True, **kwargs):
        if "FROM cluster_metadata m" in query and "score_cluster" not in query:
            return []
        if "SELECT category, topic, COUNT(DISTINCT cluster_id) as n" in query:
            assert "FROM articles" in query
            assert "COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '24 hours'" in query
            return [
                {"category": "Evropa", "topic": "Sport", "n": 3},
                {"category": "Srbija", "topic": "Politika", "n": 4},
            ]
        if "SELECT subcategory, COUNT(DISTINCT cluster_id) as n" in query:
            return [{"subcategory": "Beograd", "n": 2}]
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute.side_effect = execute_side_effect

    with (
        patch("routes.system.cached_response", return_value=None),
        patch("routes.system.set_cache"),
        patch("routes.intelligence.get_top_entities", new=AsyncMock(return_value=[])),
    ):
        data = asyncio.run(system.get_navigation())

    geography = data["sections"][0]["items"]
    news_items = data["sections"][1]["items"]
    # Match on href: display labels are localized (MK default), hrefs carry the stable key.
    assert next(item for item in geography if item["href"].endswith("category=Evropa"))["count"] == 3
    assert next(item for item in news_items if item["href"].endswith("topic=Sport"))["count"] == 3
    assert next(item for item in news_items if item["href"].endswith("topic=Politika"))["count"] == 4


def test_editorial_signals_prefer_ingested_at_for_freshness(mock_all):
    import routes.news as news

    arts = [
        {
            "title": "Sobranieto otvori rasprava za budzetot",
            "source": "MIA",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T08:00:00Z",
            "ingested_at": "2026-04-22T18:10:00Z",
        },
        {
            "title": "Telma: raspravata za budzetot prodolzuva",
            "source": "Telma",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T07:55:00Z",
            "ingested_at": "2026-04-22T18:05:00Z",
        },
    ]

    signals = news._compute_editorial_signals(arts, cluster_score=2.5, homepage_score=2.0)

    assert signals["story_state"] in {"breaking", "confirmed", "developing", "stale"}
    assert signals["live_now_fit"] in (True, False)


def test_synthesis_homepage_boost(mock_all):
    import routes.news as news

    async def execute_side_effect(query, params=None, fetch=True, **kwargs):
        if "FROM articles a" in query and "GROUP BY a.cluster_id ORDER BY last_article DESC" in query:
            return [
                {"cluster_id": "c1", "last_article": "2026-04-22T18:10:00Z"},
                {"cluster_id": "c2", "last_article": "2026-04-22T18:09:00Z"},
            ]
        if "FROM cluster_metadata" in query:
            return [
                {"cluster_id": "c1", "representative_image": None, "dominant_color": None},
                {"cluster_id": "c2", "representative_image": None, "dominant_color": None},
            ]
        if "FROM articles" in query:
            return [
                {
                    "cluster_id": "c1",
                    "title": "Cluster 1 main",
                    "source": "A",
                    "created_at": "2026-04-22T18:10:00Z",
                    "category": "Srbija",
                },
                {
                    "cluster_id": "c2",
                    "title": "Cluster 2 main",
                    "source": "B",
                    "created_at": "2026-04-22T18:09:00Z",
                    "category": "Srbija",
                },
            ]
        if "FROM cluster_summaries" in query:
            return []
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute.side_effect = execute_side_effect

    # Mock c2 to have an active synthesis, and c1 to not have one
    async def get_synthesis_ids(cluster_ids, lang=None):
        return ["c2"] if "c2" in cluster_ids else []

    mock_all["db"].async_get_synthesis_ids.side_effect = get_synthesis_ids

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache"),
        patch("routes.news.score_cluster", return_value=1.0),
        # Give both clusters the same base score of 10.0
        patch("routes.news.score_cluster_for_homepage", return_value=10.0),
    ):
        data = asyncio.run(news.get_news(sort="score", page_size=10))

    assert data["status"] == "success"
    # c2 must have bubbled to the top (index 0) due to 1.25x synthesis boost
    clusters = data["clusters"]
    assert len(clusters) == 2
    assert clusters[0]["cluster_id"] == "c2"
    assert clusters[0]["has_synthesis"] is True
    # homepage_score must be boosted to 12.5
    assert clusters[0]["homepage_score"] == 12.5

    assert clusters[1]["cluster_id"] == "c1"
    assert clusters[1]["has_synthesis"] is False
    assert clusters[1]["homepage_score"] == 10.0
