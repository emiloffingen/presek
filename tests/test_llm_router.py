import datetime
import os
from contextlib import contextmanager
from unittest.mock import patch

from core.llm_router import SmartModelRouter


@contextmanager
def _router_env(*, local_available: bool = False, **env_overrides):
    """Isolate router decisions from the host machine and .env."""
    env = {
        "FREE_API_KEYS_ENABLED": "false",
        "ROUTER_AB_TESTING": "false",
        "LOCAL_SYNTHESIS_PREFER_LOCAL": "true",
        "LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE": "true",
    }
    env.update(env_overrides)
    with (
        patch("core.llm_router._local_model_available", return_value=local_available),
        patch.dict(os.environ, env, clear=True),
    ):
        yield


def test_route_cluster_empty():
    assert SmartModelRouter.route_cluster([]) == "enhanced_fallback"


def test_route_cluster_low_complexity():
    articles = [
        {"title": "Obicna vest o vremenu", "description": "Danas ce sijati sunce na Balkanu."},
        {"title": "Jos jedna vest o vremenu", "description": "Meteorolozi najavljuju toplo leto."},
    ]
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"

    with _router_env(
        local_available=True,
        LOCAL_MODEL_PATH="/path/to/model",
        LOCAL_SYNTHESIS_PREFER_LOCAL="true",
    ):
        assert SmartModelRouter.route_cluster(articles) == "local"

    with _router_env(
        local_available=False,
        LOCAL_MODEL_PATH="/path/to/model",
    ):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_medium_complexity_by_count():
    articles = [
        {"title": "Vest 1", "description": "Nesto se dogodilo."},
        {"title": "Vest 2", "description": "Nesto se dogodilo."},
        {"title": "Vest 3", "description": "Nesto se dogodilo."},
    ]
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_medium_complexity_by_weight():
    articles = [
        {"title": "Vlada donela odluku", "description": "Novi detalji o sednici vlade."},
    ]
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_medium_complexity_local_model():
    articles = [
        {"title": "Vest 1", "description": "Nesto se dogodilo."},
        {"title": "Vest 2", "description": "Nesto se dogodilo."},
        {"title": "Vest 3", "description": "Nesto se dogodilo."},
    ]
    with _router_env(
        local_available=True,
        LOCAL_MODEL_PATH="/path/to/model",
        LOCAL_SYNTHESIS_PREFER_LOCAL="true",
    ):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_high_complexity_large_cluster():
    articles = [{"title": f"Vest {i}", "description": "Detalji."} for i in range(5)]
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_large"

    with _router_env(
        local_available=True,
        LOCAL_MODEL_PATH="/path/to/model",
        LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE="false",
        LOCAL_SYNTHESIS_PREFER_LOCAL="true",
    ):
        assert SmartModelRouter.route_cluster(articles) == "mistral_large"


def test_route_cluster_high_complexity_medium_with_weight():
    articles = [
        {"title": "Izbori i glasanje", "description": "Politicka situacija."},
        {"title": "Sednica parlamenta", "description": "Diskusija o zakonu."},
        {"title": "Saopstenje vlada", "description": "Detalji odluke."},
    ]
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_large"

    with _router_env(
        local_available=True,
        LOCAL_MODEL_PATH="/path/to/model",
        LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE="false",
        LOCAL_SYNTHESIS_PREFER_LOCAL="true",
    ):
        assert SmartModelRouter.route_cluster(articles) == "mistral_large"


def test_route_cluster_high_complexity_sports_conflict():
    articles = [
        {"title": "Partizan pobedio Zvezdu sa 3:1", "description": "Neverovatan mec."},
        {"title": "Zvezda savladala Partizan rezultatom 2:0", "description": "Veliki derbi."},
    ]
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_large"


def test_route_cluster_free_api_mode():
    articles = [
        {"title": "Obicna vest o vremenu", "description": "Danas ce sijati sunce."},
        {"title": "Jos jedna vest o vremenu", "description": "Toplo leto."},
    ]
    with _router_env(local_available=True, FREE_API_KEYS_ENABLED="true"):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_avoids_local_when_quality_is_low():
    articles = [
        {"title": "Obicna vest o vremenu", "description": "Danas ce sijati sunce."},
        {"title": "Jos jedna vest o vremenu", "description": "Toplo leto."},
    ]
    SmartModelRouter._provider_quality = {
        "local": [
            {"cluster_id": f"c{i}", "score": 0.72, "timestamp": datetime.datetime.now()}
            for i in range(6)
        ]
    }
    with _router_env(
        local_available=True,
        LOCAL_MODEL_PATH="/path/to/model",
        LOCAL_SYNTHESIS_PREFER_LOCAL="true",
    ):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_upgrades_small_when_quality_is_low_on_weighted_story():
    articles = [
        {"title": "Vlada donela odluku", "description": "Novi detalji o sednici vlade."},
    ]
    SmartModelRouter._provider_quality = {
        "mistral_small": [
            {"cluster_id": f"c{i}", "score": 0.78, "timestamp": datetime.datetime.now()}
            for i in range(6)
        ]
    }
    with _router_env(local_available=False):
        assert SmartModelRouter.route_cluster(articles) == "mistral_large"


def test_route_cluster_avoids_local_for_multi_source_clusters():
    articles = [
        {"title": "Vest 1", "description": "Detalji."},
        {"title": "Vest 2", "description": "Detalji."},
        {"title": "Vest 3", "description": "Detalji."},
    ]
    with _router_env(
        local_available=True,
        LOCAL_MODEL_PATH="/path/to/model",
        LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE="false",
        LOCAL_SYNTHESIS_PREFER_LOCAL="true",
    ):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"
