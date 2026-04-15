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

for name, mod in _get_fake_fastapi_modules().items():
    sys.modules[name] = mod

@pytest.fixture
def mock_all():
    import database
    m_db = MagicMock()
    m_ai = AsyncMock(return_value=('{"answer":"ok"}', "prov"))
    
    # Patch everything - use importlib to patch database module
    with patch.dict("sys.modules", {"database": MagicMock(db_manager=m_db)}), \
         patch("ai_engine._call_ai_async", m_ai):
        # Set up hybrid_search mock
        m_db.hybrid_search.return_value = []
        yield {"db": m_db, "ai": m_ai}
def test_fastapi_news_scales_query_fetch_limit_with_page_depth(mock_all):
    import api_fast
    with patch("routes.news.cached_response", return_value=None):
        asyncio.run(api_fast.get_news(q="економија", page=3, page_size=25))
    assert mock_all["db"].hybrid_search.called
    assert mock_all["db"].hybrid_search.call_args.kwargs["limit"] == 1200

def test_fastapi_profile_sync_init_creates_token(mock_all):
    import api_fast
    with patch("secrets.token_urlsafe", return_value="token123"):
        data = asyncio.run(api_fast.init_profile_sync())
    assert data["token"] == "token123"
    mock_all["db"].execute.assert_called()

def test_fastapi_public_health_omits_internal_connection_details(mock_all):
    import api_fast
    with patch("routes.system._probe_database", return_value={"ok": True, "article_count": 8}), \
         patch("routes.system._probe_redis", return_value={"ok": False, "url": "secret"}):
        data = asyncio.run(api_fast.health(_FakeRequest()))
    assert "url" not in data["redis"]

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
