import importlib
import re
import sys
import types


def _install_fake_fastapi():
    fake_fastapi = types.ModuleType("fastapi")
    fake_responses = types.ModuleType("fastapi.responses")

    class _FakeRouter:
        def get(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

    class _FakeRequest:
        pass

    class _FakeHTTPException(Exception):
        def __init__(self, status_code, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _FakeJSONResponse:
        def __init__(self, status_code=200, content=None):
            self.status_code = status_code
            self.content = content

    fake_fastapi.APIRouter = _FakeRouter
    fake_fastapi.Request = _FakeRequest
    fake_fastapi.HTTPException = _FakeHTTPException
    fake_responses.JSONResponse = _FakeJSONResponse

    original = {
        "fastapi": sys.modules.get("fastapi"),
        "fastapi.responses": sys.modules.get("fastapi.responses"),
    }
    sys.modules["fastapi"] = fake_fastapi
    sys.modules["fastapi.responses"] = fake_responses
    return original


def _load_home_module():
    original_fastapi = _install_fake_fastapi()
    original_modules = {
        "utils": sys.modules.get("utils"),
        "routes.common": sys.modules.get("routes.common"),
        "routes.intelligence": sys.modules.get("routes.intelligence"),
        "routes.news": sys.modules.get("routes.news"),
        "routes.stats": sys.modules.get("routes.stats"),
        "routes.system": sys.modules.get("routes.system"),
    }

    fake_utils = types.ModuleType("utils")
    fake_utils.cached_response = lambda *_args, **_kwargs: None
    fake_utils.set_cache = lambda *_args, **_kwargs: None

    fake_common = types.ModuleType("routes.common")

    def _fake_clean_and_decode(text):
        cleaned = str(text or "").replace("&amp;", "&").replace("&quot;", '"').strip()
        cleaned = re.sub(r"Read\s+More\s*[»>\-]*\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Прочитај\s+повеќе\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    fake_common.cleanAndDecode = _fake_clean_and_decode

    fake_intelligence = types.ModuleType("routes.intelligence")
    fake_intelligence.get_top_entities = lambda *args, **kwargs: []

    fake_news = types.ModuleType("routes.news")
    fake_news.get_news = lambda *args, **kwargs: {}

    fake_stats = types.ModuleType("routes.stats")
    fake_stats.get_briefing = lambda *args, **kwargs: {}
    fake_stats.get_stats_summary = lambda *args, **kwargs: {}

    fake_system = types.ModuleType("routes.system")
    fake_system.get_trending_route = lambda *args, **kwargs: []

    sys.modules["utils"] = fake_utils
    sys.modules["routes.common"] = fake_common
    sys.modules["routes.intelligence"] = fake_intelligence
    sys.modules["routes.news"] = fake_news
    sys.modules["routes.stats"] = fake_stats
    sys.modules["routes.system"] = fake_system
    sys.modules.pop("routes.home", None)
    try:
        return importlib.import_module("routes.home")
    finally:
        for module_name, module_value in original_fastapi.items():
            if module_value is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = module_value
        for module_name, module_value in original_modules.items():
            if module_value is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = module_value


def test_title_looks_like_feature_ignores_scrape_noise():
    home = _load_home_module()

    assert home._title_looks_like_feature("Прочитај повеќе")
    assert home._title_looks_like_feature("Read More »")


def test_rank_latest_wire_articles_dedupes_cleaned_titles():
    home = _load_home_module()

    items = [
        {
            "title": "Владата усвои мерки &amp; пакет",
            "topic": "Политика",
            "category": "Srbija",
            "created_at": "2026-04-22T10:00:00",
            "source": "A",
        },
        {
            "title": "Владата усвои мерки & пакет",
            "topic": "Политика",
            "category": "Srbija",
            "created_at": "2026-04-22T10:05:00",
            "source": "B",
        },
    ]

    ranked = home._rank_latest_wire_articles(items, limit=15)

    assert len(ranked) == 1


def test_extract_preview_summary_parses_jsonish_summary_blob():
    home = _load_home_module()

    article = {
        "summary": "",
        "description": '{"summary":"Чисто резиме","text":"Резервно"}',
    }

    assert home._extract_preview_summary(article) == "Чисто резиме"


def test_build_lead_display_returns_cleaned_preview_fields():
    home = _load_home_module()

    cluster = {
        "is_breaking": True,
        "articles": [
            {
                "title": "Владата &amp; мерки",
                "summary": "Прочитај повеќе",
                "description": "Опис",
            },
            {"title": "Втор агол"},
        ],
    }

    display = home._build_lead_display(cluster)

    assert display["title"] == "Владата & мерки"
    assert display["summary"] == ""
    assert display["signal"] == "Најбрз развој во денот"


def test_decorate_cluster_display_adds_display_fields_to_articles():
    home = _load_home_module()

    cluster = {
        "cluster_id": "abc123",
        "articles": [
            {
                "title": "Владата &amp; мерки",
                "summary": "",
                "description": "Опис",
            }
        ],
    }

    decorated = home._decorate_cluster_display(cluster)

    assert decorated["articles"][0]["display_title"] == "Владата & мерки"
    assert decorated["articles"][0]["display_summary"] == "Опис"
