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
    fake_fastapi.Path = _FakeRouter  # Use a dummy or mock object
    fake_fastapi.Query = _FakeRouter
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
        "routes": sys.modules.get("routes"),
        "routes.home": sys.modules.get("routes.home"),
        "utils": sys.modules.get("utils"),
        "routes.common": sys.modules.get("routes.common"),
        "routes.intelligence": sys.modules.get("routes.intelligence"),
        "routes.news": sys.modules.get("routes.news"),
        "routes.stats": sys.modules.get("routes.stats"),
        "routes.system": sys.modules.get("routes.system"),
        "core.api_errors": sys.modules.get("core.api_errors"),
        "core.audio_service": sys.modules.get("core.audio_service"),
        "core.queue_status": sys.modules.get("core.queue_status"),
        "nlp": sys.modules.get("nlp"),
    }

    fake_utils = types.ModuleType("utils")
    fake_utils.cached_response = lambda *_args, **_kwargs: None
    fake_utils.set_cache = lambda *_args, **_kwargs: None
    fake_utils.redis_client = None
    fake_utils.record_runtime_event = lambda *_args, **_kwargs: None

    fake_nlp = types.ModuleType("nlp")
    fake_nlp.normalize_focus_entity_surface = lambda name: str(name or "").strip()

    fake_api_errors = types.ModuleType("core.api_errors")
    fake_api_errors.soft_error = lambda *_args, **_kwargs: None

    fake_audio_service = types.ModuleType("core.audio_service")

    class _FakeAudioService:
        pass

    fake_audio_service.AudioService = _FakeAudioService

    fake_queue_status = types.ModuleType("core.queue_status")
    fake_queue_status.reader_pipeline_status = lambda *_args, **_kwargs: {}

    fake_common = types.ModuleType("routes.common")

    def _fake_clean_and_decode(text):
        cleaned = str(text or "").replace("&amp;", "&").replace("&quot;", '"').strip()
        cleaned = re.sub(r"Read\s+More\s*[»>\-]*\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Procitaj\s+povece\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    fake_common.cleanAndDecode = _fake_clean_and_decode

    fake_intelligence = types.ModuleType("routes.intelligence")
    fake_intelligence.get_top_entities = lambda *args, **kwargs: []

    fake_news = types.ModuleType("routes.news")
    fake_news.get_news = lambda *args, **kwargs: {}
    fake_news.fetch_news_data = lambda *args, **kwargs: {}

    fake_stats = types.ModuleType("routes.stats")
    fake_stats.get_briefing = lambda *args, **kwargs: {}
    fake_stats.get_stats_summary = lambda *args, **kwargs: {}

    fake_system = types.ModuleType("routes.system")
    fake_system.get_trending_route = lambda *args, **kwargs: []

    sys.modules["utils"] = fake_utils
    sys.modules["core.api_errors"] = fake_api_errors
    sys.modules["core.audio_service"] = fake_audio_service
    sys.modules["core.queue_status"] = fake_queue_status
    sys.modules["nlp"] = fake_nlp
    sys.modules["routes.common"] = fake_common
    sys.modules["routes.intelligence"] = fake_intelligence
    sys.modules["routes.news"] = fake_news
    sys.modules["routes.stats"] = fake_stats
    sys.modules["routes.system"] = fake_system
    sys.modules.pop("routes.home", None)
    sys.modules.pop("routes", None)
    try:
        mod = importlib.import_module("routes.home")
        return mod
    finally:
        sys.modules.pop("routes.home", None)
        sys.modules.pop("routes", None)
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

    assert home._title_looks_like_feature("Procitaj povece")
    assert home._title_looks_like_feature("Read More »")


def test_rank_latest_wire_articles_dedupes_cleaned_titles():
    home = _load_home_module()

    items = [
        {
            "title": "Vladata usvoi merki &amp; paket",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T10:00:00",
            "source": "A",
        },
        {
            "title": "Vladata usvoi merki & paket",
            "topic": "Politika",
            "category": "Srbija",
            "created_at": "2026-04-22T10:05:00",
            "source": "B",
        },
    ]

    ranked = home._rank_latest_wire_articles(items, limit=15)

    assert len(ranked) == 1


def test_extract_preview_summary_truncates_long_text():
    home = _load_home_module()

    article = {
        "summary": "A" * 250,
        "description": "",
    }

    result = home._extract_preview_summary(article)
    assert len(result) == 200
    assert result.endswith("...")


def test_extract_preview_summary_returns_short_text_unchanged():
    home = _load_home_module()

    article = {
        "summary": "Short text",
        "description": "",
    }

    assert home._extract_preview_summary(article) == "Short text"


def test_build_lead_display_returns_cleaned_preview_fields():
    home = _load_home_module()

    cluster = {
        "is_breaking": True,
        "articles": [
            {
                "title": "Vladata &amp; merki",
                "summary": "Procitaj povece",
                "description": "Opis",
            },
            {"title": "Vtor ugao"},
        ],
    }

    display = home._build_lead_display(cluster)

    assert display["title"] == "Vladata & merki"
    assert display["summary"] == "Procitaj povece"
    assert display["signal"] == "Најбрз развој денес"


def test_decorate_cluster_display_adds_display_fields_to_articles():
    home = _load_home_module()

    cluster = {
        "cluster_id": "abc123",
        "articles": [
            {
                "title": "Vladata &amp; merki",
                "summary": "",
                "description": "Opis",
            }
        ],
    }

    decorated = home._decorate_cluster_display(cluster)

    assert decorated["articles"][0]["display_title"] == "Vladata & merki"
    assert decorated["articles"][0]["display_summary"] == "Opis"





def test_fill_developing_clusters_backfills_when_primary_pool_empty():
    home = _load_home_module()

    feed = [
        {
            "cluster_id": "wire-only",
            "homepage_score": 0.01,
            "has_synthesis": False,
            "articles": [{"title": "Singleton", "source": "A"}],
        },
        {
            "cluster_id": "scored",
            "homepage_score": 2.5,
            "has_synthesis": True,
            "source_count": 1,
            "articles": [{"title": "Lead story", "source": "B"}],
        },
        {
            "cluster_id": "corroborated",
            "homepage_score": 1.8,
            "has_synthesis": False,
            "source_count": 3,
            "articles": [{"title": "Multi", "source": "C"}],
        },
    ]

    developing = home._fill_developing_clusters(feed, exclude_ids=set(), limit=10, backfill_min=2)

    assert [cluster["cluster_id"] for cluster in developing] == ["corroborated", "scored"]



