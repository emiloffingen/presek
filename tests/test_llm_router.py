import os
from unittest.mock import patch
from core.llm_router import SmartModelRouter


def test_route_cluster_empty():
    assert SmartModelRouter.route_cluster([]) == "enhanced_fallback"


def test_route_cluster_low_complexity():
    articles = [
        {"title": "Obicna vest o vremenu", "description": "Danas ce sijati sunce na Balkanu."},
        {"title": "Jos jedna vest o vremenu", "description": "Meteorolozi najavljuju toplo leto."}
    ]
    assert SmartModelRouter.route_cluster(articles) == "enhanced_fallback"


def test_route_cluster_medium_complexity_by_count():
    articles = [
        {"title": "Vest 1", "description": "Nesto se dogodilo."},
        {"title": "Vest 2", "description": "Nesto se dogodilo."},
        {"title": "Vest 3", "description": "Nesto se dogodilo."}
    ]
    # No LOCAL_MODEL_PATH or GGUF file, should fall back to mistral_small
    with patch("os.path.exists", return_value=False), patch.dict(os.environ, {}, clear=True):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_medium_complexity_by_weight():
    articles = [
        {"title": "Vlada donela odluku", "description": "Novi detalji o sednici vlade."},
    ]
    with patch("os.path.exists", return_value=False), patch.dict(os.environ, {}, clear=True):
        assert SmartModelRouter.route_cluster(articles) == "mistral_small"


def test_route_cluster_medium_complexity_local_model():
    articles = [
        {"title": "Vest 1", "description": "Nesto se dogodilo."},
        {"title": "Vest 2", "description": "Nesto se dogodilo."},
        {"title": "Vest 3", "description": "Nesto se dogodilo."}
    ]
    # With LOCAL_MODEL_PATH, should route to local
    with patch.dict(os.environ, {"LOCAL_MODEL_PATH": "/path/to/model"}):
        assert SmartModelRouter.route_cluster(articles) == "local"


def test_route_cluster_high_complexity_large_cluster():
    articles = [
        {"title": f"Vest {i}", "description": "Detalji."} for i in range(5)
    ]
    assert SmartModelRouter.route_cluster(articles) == "mistral_large"


def test_route_cluster_high_complexity_medium_with_weight():
    articles = [
        {"title": "Izbori i glasanje", "description": "Politicka situacija."},
        {"title": "Sednica parlamenta", "description": "Diskusija o zakonu."},
        {"title": "Saopstenje vlada", "description": "Detalji odluke."}
    ]
    assert SmartModelRouter.route_cluster(articles) == "mistral_large"


def test_route_cluster_high_complexity_sports_conflict():
    articles = [
        {"title": "Partizan pobedio Zvezdu sa 3:1", "description": "Neverovatan mec."},
        {"title": "Zvezda savladala Partizan rezultatom 2:0", "description": "Veliki derbi."}
    ]
    assert SmartModelRouter.route_cluster(articles) == "mistral_large"
