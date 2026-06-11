def test_ingestion_imports_intelligence_secondary_deferred():
    import inspect

    import core.ingestion as ingestion
    from tasks.intelligence import intelligence_secondary_deferred

    source = inspect.getsource(ingestion)
    assert "intelligence_secondary_deferred" in source
    assert callable(intelligence_secondary_deferred)
