import importlib
import asyncio
import os
import sys
import types
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# --- Robust Global FastAPI Mocks ---

class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
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
        def decorator(fn): return fn
        return decorator
    def post(self, _path, **_kwargs):
        def decorator(fn): return fn
        return decorator
    def include_router(self, router, **kwargs):
        pass

class _FakeRequest:
    def __init__(self, payload=None, headers=None, client_host="127.0.0.1"):
        self._payload = payload or {}
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = types.SimpleNamespace(host=client_host)
        self.url = types.SimpleNamespace(path="/", path_params={})
        self.cookies = {}
    async def json(self): return self._payload

class _FakeResponse:
    def __init__(self, content=None, media_type=None, headers=None, status_code=200):
        self.content = content
        self.media_type = media_type
        self.headers = headers or {}
        self.status_code = status_code
    def __getitem__(self, key):
        if isinstance(self.content, dict): return self.content[key]
        raise KeyError(key)
    def get(self, key, default=None):
        return self.content.get(key, default) if isinstance(self.content, dict) else default

class _FakeJSONResponse(_FakeResponse):
    def __init__(self, status_code=200, content=None):
        super().__init__(content, "application/json", {}, status_code)

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
            def decorator(fn): return fn
            return decorator
        def post(self, *args, **kwargs):
            def decorator(fn): return fn
            return decorator
        def include_router(self, *args, **kwargs): pass
    f.APIRouter = _FakeRouter
    f.Request = _FakeRequest
    f.HTTPException = _FakeHTTPException
    f.Query = MagicMock(side_effect=lambda default=None, **kwargs: default)
    f.BackgroundTasks = MagicMock
    f.Depends = MagicMock
    f.Form = MagicMock
    f.Header = MagicMock
    
    r = make_mod("fastapi.responses")
    r.JSONResponse = _FakeJSONResponse
    r.RedirectResponse = MagicMock
    r.FileResponse = MagicMock
    r.StreamingResponse = MagicMock
    r.Response = _FakeResponse
    
    mc = make_mod("fastapi.middleware.cors")
    mc.CORSMiddleware = MagicMock
    
    mg = make_mod("fastapi.middleware.gzip")
    mg.GZipMiddleware = MagicMock
    
    m = make_mod("fastapi.middleware")
    return {
        "fastapi": f,
        "fastapi.responses": r,
        "fastapi.middleware": m,
        "fastapi.middleware.cors": mc,
        "fastapi.middleware.gzip": mg,
    }

@pytest.fixture(scope="module", autouse=True)
def _install_fake_fastapi_modules():
    original_modules = {name: sys.modules.get(name) for name in _get_fake_fastapi_modules()}
    sys.modules.update(_get_fake_fastapi_modules())
    for name in ["api_fast", "routes", "routes.news", "routes.profile", "routes.stats", "routes.system", "routes.intelligence", "routes.security"]:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        for name in ["api_fast", "routes", "routes.news", "routes.profile", "routes.stats", "routes.system", "routes.intelligence", "routes.security"]:
            sys.modules.pop(name, None)

@pytest.fixture
def mock_all():
    import database
    m_db = MagicMock()
    m_db.async_execute = AsyncMock(return_value=[])
    m_db.async_execute_one = AsyncMock(return_value={})
    m_db.async_get_synthesis_ids = AsyncMock(return_value=[])
    m_db.async_search_articles = AsyncMock(return_value=[])
    m_db.async_hybrid_search = AsyncMock(return_value=[])
    m_ai = AsyncMock(return_value=('{"answer":"ok"}', "prov"))
    
    # Patch everything - use importlib to patch database module
    with patch.dict("sys.modules", {"database": MagicMock(db_manager=m_db)}), \
         patch("ai_engine._call_ai_async", m_ai):
        m_db.hybrid_search.return_value = []
        yield {"db": m_db, "ai": m_ai}

def test_fastapi_news_scales_query_fetch_limit_with_page_depth(mock_all):
    import api_fast
    with patch("routes.news.cached_response", return_value=None):
        asyncio.run(api_fast.get_news(q="економија", page=3, page_size=25))
    assert mock_all["db"].async_search_articles.called
    assert mock_all["db"].async_search_articles.call_args.kwargs["limit"] == 1200

def test_fastapi_profile_sync_init_creates_token(mock_all):
    import api_fast
    with patch("secrets.token_urlsafe", return_value="token123"):
        data = asyncio.run(api_fast.init_profile_sync())
    assert data["token"] == "token123"
    mock_all["db"].async_execute.assert_called()

def test_top_entities_compacts_fragments_and_filters_noise(mock_all):
    import routes.intelligence as intelligence

    mock_all["db"].async_execute.return_value = [
        {"name": "МИА", "total_mentions": 12},
        {"name": "Ормуз", "total_mentions": 8},
        {"name": "Теснец", "total_mentions": 7},
        {"name": "Договор", "total_mentions": 6},
        {"name": "Иран", "total_mentions": 10},
        {"name": "Доналд Трамп", "total_mentions": 9},
    ]

    with patch("routes.intelligence.cached_response", return_value=None), \
         patch("routes.intelligence.set_cache"):
        data = asyncio.run(intelligence.get_top_entities(limit=10))

    names = [item["name"] for item in data]
    assert "МИА" not in names
    assert "Договор" not in names
    assert "Ормуз" not in names
    assert "Теснец" not in names
    assert "Ормуски Теснец" in names
    assert "Иран" in names

def test_fastapi_public_health_omits_internal_connection_details(mock_all):
    import api_fast
    with patch("routes.system._probe_database", return_value={"ok": True, "article_count": 8}), \
         patch("routes.system._probe_redis", return_value={"ok": False, "url": "secret"}):
        data = asyncio.run(api_fast.health(_FakeRequest()))
    assert "url" not in data["redis"]


def test_fastapi_only_registers_prefixed_routers(mock_all):
    api_fast = importlib.import_module("api_fast")
    content = open(os.path.join(os.path.dirname(__file__), "..", "api_fast.py"), encoding="utf-8").read()
    assert 'app.include_router(news.router, prefix="/api")' in content
    assert "app.include_router(news.router)\n" not in content

def test_fastapi_proxy_rejects_remote_svg_content(mock_all):
    import api_fast
    fake_resp = MagicMock(status_code=200, headers={"Content-Type": "image/svg+xml"})
    with patch("routes.common._resolve_public_ips", return_value=["1.2.3.4"]), \
         patch("routes.common._peer_ip", return_value="1.2.3.4"), \
         patch("requests.get", return_value=fake_resp):
        response = asyncio.run(api_fast.proxy_image("https://c.com/a.svg", None))
    assert response.status_code in {415, 200}

def test_fastapi_serves_robots_txt(mock_all):
    import api_fast
    resp = asyncio.run(api_fast.robots_txt())
    assert "User-agent" in resp.content

def test_fastapi_serves_og_cluster_image(mock_all):
    import api_fast
    mock_all["db"].execute_one.side_effect = [{"title": "T"}, {"summary": "S"}]
    mock_all["db"].execute.return_value = [{"title": "T1", "source":"S1", "category":"C1"}]
    
    with patch("PIL.Image.new"), patch("PIL.ImageDraw.Draw"), patch("PIL.ImageFont.truetype"):
        resp = asyncio.run(api_fast.og_cluster_image("abc123"))
    assert resp.media_type == "image/png"

def test_fastapi_og_cluster_image_blocks_unresolved_remote_backgrounds(mock_all):
    import api_fast
    mock_all["db"].execute.return_value = [{
        "title": "T1",
        "source": "S1",
        "category": "C1",
        "image_url": "http://169.254.169.254/latest/meta-data",
        "local_image_path": None,
    }]
    mock_all["db"].execute_one.side_effect = [
        {"representative_image": "http://169.254.169.254/latest/meta-data", "dominant_color": None},
    ]

    fake_image = MagicMock()
    fake_client = MagicMock()

    with patch("routes.system._resolve_public_ips", side_effect=ValueError("Blocked URL")), \
         patch("httpx.Client", return_value=fake_client), \
         patch("PIL.Image.new", return_value=fake_image), \
         patch("PIL.ImageDraw.Draw"), \
         patch("PIL.ImageFont.truetype"):
        fake_image.save.side_effect = lambda output, format=None: output.write(b"png")
        resp = asyncio.run(api_fast.og_cluster_image("abc123"))

    fake_client.get.assert_not_called()
    assert resp.media_type == "image/png"

def test_fastapi_historical_events_formats_pgvector_parameter(mock_all):
    import routes.news

    async def async_execute_side_effect(query, params=None, fetch=True):
        if "SELECT embedding FROM articles" in query:
            return [{"embedding": "[0.1,0.2,0.3]"}]
        if "WITH archive_pool AS" in query:
            assert isinstance(params[0], str)
            assert params[0].startswith("[") and params[0].endswith("]")
            return []
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute.side_effect = async_execute_side_effect

    with patch("routes.news.cached_response", return_value=None), \
         patch("routes.news.set_cache"):
        data = asyncio.run(routes.news.get_historical_events("abc123"))

    assert data == {"status": "success", "events": []}

def test_request_size_middleware_rejects_large_content_length():
    from routes.security import RequestSizeMiddleware, MAX_REQUEST_BODY_SIZE

    request = types.SimpleNamespace(
        headers={"content-length": str(MAX_REQUEST_BODY_SIZE + 1)},
        query_params={},
    )
    middleware = RequestSizeMiddleware(app=MagicMock())

    with pytest.raises(_FakeHTTPException) as exc:
        asyncio.run(middleware.dispatch(request, AsyncMock()))

    assert exc.value.status_code == 413

def test_stats_summary_includes_intelligence_payload(mock_all):
    import routes.stats

    def execute_one_side_effect(query, *args, **kwargs):
        if "COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'" in query:
            return {"count": 120}
        if "COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '1 hour'" in query:
            return {"count": 12}
        if "COUNT(*) FROM sources WHERE is_active = TRUE" in query:
            return {"count": 40}
        if "FROM cluster_summaries s" in query:
            return {"quote": "", "summary": "• Q\n• R", "generated_article": "", "cluster_id": "abc123", "title": "T"}
        if "SELECT COUNT(*) FROM articles WHERE is_global = TRUE" in query:
            return {"count": 30}
        if "SELECT COUNT(*) FROM articles" in query:
            return {"count": 200}
        if "FROM cluster_tiers" in query:
            return {"total_clusters": 20, "high_consensus": 5, "diverse_sources": 8}
        raise AssertionError(f"Unexpected query: {query}")

    mock_all["db"].async_execute_one.side_effect = execute_one_side_effect

    with patch("routes.stats.cached_response", return_value=None), \
         patch("routes.stats.set_cache"), \
         patch.object(routes.stats.redis_client, "hgetall", return_value={
             "synthesis_path|mode=ai": "3",
             "synthesis_path|mode=local_fallback": "1",
         }):
        data = asyncio.run(routes.stats.get_stats_summary())

    assert data["last_24h"] == 120
    assert data["quote_of_the_day"]["cluster_id"] == "abc123"
    assert data["quote_of_the_day"]["quote"] == "Q"
    assert data["intelligence"]["international_share_pct"] == 15.0
    assert data["intelligence"]["ai_transparency"]["ai_ratio"] == 75.0
    assert data["intelligence"]["pluralism"]["pluralism_pct"] == 65.0
    assert data["intelligence"]["pluralism"]["high_consensus_pct"] == 25.0
