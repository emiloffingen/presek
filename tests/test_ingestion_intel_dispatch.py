def test_ingestion_imports_intelligence_soft_deferred():
    from pathlib import Path

    from tasks.intelligence import intelligence_soft_deferred
    from tasks.utils import crawl_dispatches_deferred

    source = Path("core/ingestion.py").read_text(encoding="utf-8")
    assert "intelligence_soft_deferred" in source
    assert "crawl_dispatches_deferred" in source
    assert callable(intelligence_soft_deferred)
    assert callable(crawl_dispatches_deferred)
