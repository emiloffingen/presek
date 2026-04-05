import importlib
import asyncio
import os
import sys
import types
from unittest.mock import patch, MagicMock

class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _FakeFastAPI:
    def __init__(self, *args, **kwargs):
        self.user_middleware = []

    def add_middleware(self, cls, **options):
        self.user_middleware.append(types.SimpleNamespace(cls=cls, options=options))

    def get(self, _path, **_kwargs):
        def decorator(fn):
            return fn
        return decorator

    def post(self, _path, **_kwargs):
        def decorator(fn):
            return fn
        return decorator


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _install_fake_fastapi_modules():
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.FastAPI = _FakeFastAPI
    fastapi_mod.Request = _FakeRequest
    fastapi_mod.Query = lambda default=None, **_kwargs: default
    fastapi_mod.HTTPException = _FakeHTTPException

    responses_mod = types.ModuleType("fastapi.responses")
    responses_mod.StreamingResponse = type("StreamingResponse", (), {})
    responses_mod.JSONResponse = type("JSONResponse", (), {})

    cors_mod = types.ModuleType("fastapi.middleware.cors")
    cors_mod.CORSMiddleware = type("CORSMiddleware", (), {})

    middleware_pkg = types.ModuleType("fastapi.middleware")

    return {
        "fastapi": fastapi_mod,
        "fastapi.responses": responses_mod,
        "fastapi.middleware": middleware_pkg,
        "fastapi.middleware.cors": cors_mod,
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
