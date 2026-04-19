import os
import sys
import types
import importlib
import pytest
from unittest.mock import MagicMock


os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/presek_test")


def _install_httpx_stub():
    if "httpx" in sys.modules:
        return

    httpx = types.ModuleType("httpx")

    class RequestError(Exception):
        def __init__(self, message="", *args, request=None, response=None, **kwargs):
            super().__init__(message, *args)
            self.request = request
            self.response = response

    class HTTPStatusError(Exception):
        def __init__(self, message="", *args, request=None, response=None, **kwargs):
            super().__init__(message, *args)
            self.request = request
            self.response = response

    class Client:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            raise RuntimeError("httpx stub Client.post called without patching")

        def get(self, *args, **kwargs):
            raise RuntimeError("httpx stub Client.get called without patching")

    class _AsyncStreamContext:
        async def __aenter__(self):
            raise RuntimeError("httpx stub AsyncClient.stream called without patching")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            raise RuntimeError("httpx stub AsyncClient.post called without patching")

        def get(self, *args, **kwargs):
            raise RuntimeError("httpx stub AsyncClient.get called without patching")

        def stream(self, *args, **kwargs):
            return _AsyncStreamContext()

    httpx.RequestError = RequestError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.Client = Client
    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx


def _install_pil_stub():
    if "PIL" in sys.modules:
        return

    pil = types.ModuleType("PIL")
    image = types.ModuleType("PIL.Image")
    image_draw = types.ModuleType("PIL.ImageDraw")
    image_font = types.ModuleType("PIL.ImageFont")

    class _Resampling:
        LANCZOS = "LANCZOS"

    def _unpatched(*args, **kwargs):
        raise RuntimeError("PIL stub called without patching")

    image.Resampling = _Resampling
    image.open = _unpatched
    image.new = _unpatched
    image_draw.Draw = _unpatched
    image_font.truetype = _unpatched

    pil.Image = image
    pil.ImageDraw = image_draw
    pil.ImageFont = image_font

    sys.modules["PIL"] = pil
    sys.modules["PIL.Image"] = image
    sys.modules["PIL.ImageDraw"] = image_draw
    sys.modules["PIL.ImageFont"] = image_font


_install_httpx_stub()
_install_pil_stub()


def _install_starlette_stub():
    if "starlette" in sys.modules:
        return

    starlette = types.ModuleType("starlette")
    responses = types.ModuleType("starlette.responses")
    middleware = types.ModuleType("starlette.middleware")
    middleware_base = types.ModuleType("starlette.middleware.base")

    class Response:
        def __init__(self, content=None, status_code=200, headers=None, media_type=None):
            self.content = content
            self.status_code = status_code
            self.headers = headers or {}
            self.media_type = media_type

    class BaseHTTPMiddleware:
        def __init__(self, app=None, dispatch=None):
            self.app = app
            self.dispatch_func = dispatch

        async def dispatch(self, request, call_next):
            if self.dispatch_func:
                return await self.dispatch_func(request, call_next)
            return await call_next(request)

    responses.Response = Response
    middleware_base.BaseHTTPMiddleware = BaseHTTPMiddleware
    middleware.base = middleware_base
    starlette.responses = responses
    starlette.middleware = middleware

    sys.modules["starlette"] = starlette
    sys.modules["starlette.responses"] = responses
    sys.modules["starlette.middleware"] = middleware
    sys.modules["starlette.middleware.base"] = middleware_base


def _install_trafilatura_stub():
    if "trafilatura" in sys.modules:
        return

    trafilatura = types.ModuleType("trafilatura")
    trafilatura.extract = lambda *args, **kwargs: ""
    sys.modules["trafilatura"] = trafilatura


def _install_playwright_stub():
    if "playwright" in sys.modules:
        return

    playwright = types.ModuleType("playwright")
    async_api = types.ModuleType("playwright.async_api")

    async def async_playwright():
        raise RuntimeError("playwright stub called without patching")

    async_api.async_playwright = async_playwright
    playwright.async_api = async_api

    sys.modules["playwright"] = playwright
    sys.modules["playwright.async_api"] = async_api


_install_starlette_stub()
_install_trafilatura_stub()
_install_playwright_stub()

_REAL_DATABASE_MODULE = importlib.import_module("database")
_MODULES_TO_RELOAD = (
    "api_fast",
    "routes.news",
    "routes.profile",
    "routes.stats",
    "routes.system",
    "routes.intelligence",
    "routes.security",
)


@pytest.fixture(autouse=True)
def _restore_runtime_modules(request):
    module_name = getattr(request.module, "__name__", "")
    preserve_fake_database = module_name.endswith("test_personalized_news") or module_name.endswith("test_api_fast")

    if hasattr(request.module, "_get_fake_fastapi_modules"):
        for name, mod in request.module._get_fake_fastapi_modules().items():
            sys.modules[name] = mod

    if module_name.endswith("test_personalized_news") and hasattr(request.module, "mock_db_manager"):
        sys.modules["database"] = MagicMock(db_manager=request.module.mock_db_manager)
    elif not preserve_fake_database:
        sys.modules["database"] = _REAL_DATABASE_MODULE

    for name in _MODULES_TO_RELOAD:
        sys.modules.pop(name, None)

    yield
