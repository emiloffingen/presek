from core.config import resolve_primary_database_url


def test_resolve_primary_database_url_warns_on_replica_name(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://presek:pass@localhost/presek_replica")
    monkeypatch.delenv("DATABASE_READ_REPLICA_URL", raising=False)
    assert "presek_replica" in resolve_primary_database_url()


def test_prepared_statements_disabled_for_pooler_dsn(monkeypatch):
    import core.database as db

    monkeypatch.delenv("PRESEK_PREPARED_STATEMENTS", raising=False)
    monkeypatch.setattr(
        db,
        "DATABASE_URL",
        "postgresql://u:p@aws-0-eu-north-1.pooler.supabase.com:6543/postgres",
    )
    assert db._use_server_side_prepared_statements() is False
    assert db._pool_common_kwargs().get("prepare_threshold", "missing") is None


def test_prepared_statements_enabled_for_direct_dsn(monkeypatch):
    import core.database as db

    monkeypatch.delenv("PRESEK_PREPARED_STATEMENTS", raising=False)
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@localhost:5432/presek")
    assert db._use_server_side_prepared_statements() is True


def test_prepared_statements_env_override(monkeypatch):
    import core.database as db

    monkeypatch.setattr(
        db,
        "DATABASE_URL",
        "postgresql://u:p@aws-0-eu-north-1.pooler.supabase.com:6543/postgres",
    )
    monkeypatch.setenv("PRESEK_PREPARED_STATEMENTS", "1")
    assert db._use_server_side_prepared_statements() is True
    monkeypatch.setenv("PRESEK_PREPARED_STATEMENTS", "0")
    assert db._use_server_side_prepared_statements() is False
