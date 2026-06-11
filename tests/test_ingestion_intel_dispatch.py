def test_ingestion_imports_intelligence_soft_deferred():
    import inspect

    import core.ingestion as ingestion
    from tasks.intelligence import intelligence_soft_deferred

    source = inspect.getsource(ingestion)
    assert "intelligence_soft_deferred" in source
    assert callable(intelligence_soft_deferred)
