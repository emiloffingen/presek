import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Robust Global FastAPI Mocks ---


class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _get_fake_fastapi_modules():
    import importlib.machinery

    def make_mod(name):
        m = types.ModuleType(name)
        m.__spec__ = importlib.machinery.ModuleSpec(name, None)
        return m

    f = make_mod("fastapi")

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
    f.Request = MagicMock
    f.HTTPException = _FakeHTTPException
    f.Depends = MagicMock
    f.Header = MagicMock
    f.Query = MagicMock
    f.BackgroundTasks = MagicMock
    f.Form = MagicMock

    r = make_mod("fastapi.responses")
    r.JSONResponse = MagicMock
    r.RedirectResponse = MagicMock
    r.FileResponse = MagicMock
    r.Response = MagicMock
    r.StreamingResponse = MagicMock

    s = make_mod("starlette")
    s_resp = make_mod("starlette.responses")
    s_resp.Response = MagicMock
    s_middleware = make_mod("starlette.middleware")
    s_middleware_base = make_mod("starlette.middleware.base")
    s_middleware_base.BaseHTTPMiddleware = MagicMock
    s.responses = s_resp
    s.middleware = s_middleware
    s.middleware.base = s_middleware_base
    s.status = MagicMock

    fs = make_mod("fastapi.security")
    fs.HTTPAuthorizationCredentials = MagicMock
    fs.HTTPBearer = MagicMock
    fs.OAuth2PasswordBearer = MagicMock

    fm = make_mod("fastapi.middleware")
    fm_cors = make_mod("fastapi.middleware.cors")
    fm_cors.CORSMiddleware = MagicMock

    return {
        "fastapi": f,
        "fastapi.responses": r,
        "fastapi.security": fs,
        "fastapi.middleware": fm,
        "fastapi.middleware.cors": fm_cors,
        "starlette": s,
        "starlette.responses": s_resp,
        "starlette.middleware": s_middleware,
        "starlette.middleware.base": s_middleware_base,
        "starlette.status": MagicMock(),
    }


mock_db_manager = MagicMock()
mock_db_manager.async_execute = AsyncMock(return_value=[])
mock_db_manager.async_get_synthesis_ids = AsyncMock(return_value=[])
mock_db_manager.execute = AsyncMock(return_value=[])


@pytest.fixture(scope="module", autouse=True)
def _install_test_module_mocks():
    fake_modules = _get_fake_fastapi_modules()
    fake_modules["database"] = MagicMock(db_manager=mock_db_manager)
    original_modules = {name: sys.modules.get(name) for name in fake_modules}
    sys.modules.update(fake_modules)
    for name in ["routes", "routes.profile", "routes.news", "routes.security"]:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        for name in ["routes", "routes.profile", "routes.news", "routes.security"]:
            sys.modules.pop(name, None)


# --- End Mocks ---


def test_get_personalized_news_sync_empty_profile():
    from routes.profile import get_personalized_news_sync

    request = MagicMock()
    request.json = AsyncMock(return_value={"profile": {"recentClusters": []}})

    response = asyncio.run(get_personalized_news_sync(request))
    assert response["status"] == "success"
    assert response["results"] == []


def test_get_personalized_news_sync_with_history():
    import routes.news  # noqa: F401 — imported for side-effect: registers module in sys.modules so patch() can resolve it
    from routes.profile import get_personalized_news_sync

    # Mock data
    recent = [{"cluster_id": "c1"}]
    mock_db_manager.async_execute.side_effect = [
        # 1. Fetch embeddings for recent
        [{"embedding": [0.1] * 1536}],
        # 2. Semantic search pool
        [
            {"cluster_id": "c2", "similarity": 0.8},
        ],
        # 3. Fetch all articles for found clusters
        [
            {"cluster_id": "c2", "title": "T1", "source": "S1"},
            {"cluster_id": "c2", "title": "T2", "source": "S2"},
        ],
        # 4. Fetch metadata
        [
            {
                "cluster_id": "c2",
                "representative_image": "img.jpg",
                "dominant_color": "#fff",
            }
        ],
        # 5. Check if clusters have summaries (async_get_synthesis_ids calls async_execute)
        [{"cluster_id": "c2"}],
        # 6. Any additional calls return empty
        [],
    ]
    mock_db_manager.async_get_synthesis_ids.return_value = ["c2"]
    mock_db_manager.execute.side_effect = mock_db_manager.async_execute.side_effect

    request = MagicMock()
    request.json = AsyncMock(return_value={"profile": {"recentClusters": recent}, "limit": 5})

    with (
        patch("routes.profile.annotate_cluster_articles", side_effect=lambda x, **kw: x),
        patch("routes.profile.score_cluster", return_value=5.0),
        patch("routes.profile.is_balanced", return_value=True),
        patch("routes.profile.score_cluster_for_homepage", return_value=4.0),
        patch("routes.news._public_article_payload", side_effect=lambda x, **kw: x),
        patch("core.database.async_db", mock_db_manager),
    ):
        response = asyncio.run(get_personalized_news_sync(request))

    assert response["status"] == "success"
    assert len(response["results"]) == 1
    assert response["results"][0]["cluster_id"] == "c2"
    assert response["results"][0]["representative_image"] == "img.jpg"
    assert response["results"][0]["has_synthesis"] is True
    assert response["results"][0]["has_balanced"] is True
    assert response["results"][0]["score"] == 5.0
    assert len(response["results"][0]["articles"]) == 2


def test_get_personalized_news_sync_mk_uses_country_filter():
    from routes.profile import get_personalized_news_sync

    recent = [{"cluster_id": "c1"}]
    mock_db_manager.async_execute.reset_mock()
    mock_db_manager.async_execute.side_effect = [
        [{"embedding": [0.1] * 1536}],
        [],
    ]

    request = MagicMock()
    request.json = AsyncMock(return_value={"profile": {"recentClusters": recent}, "limit": 5, "locale": "mk"})

    with patch("routes.profile.db", mock_db_manager):
        response = asyncio.run(get_personalized_news_sync(request))

    assert response["status"] == "success"
    assert response["results"] == []
    semantic_query, semantic_params = mock_db_manager.async_execute.call_args_list[1].args
    assert "country = %s" in semantic_query
    assert semantic_params[1] == "MK"
