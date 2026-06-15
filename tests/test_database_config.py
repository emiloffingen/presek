from core.config import resolve_primary_database_url


def test_resolve_primary_database_url_warns_on_replica_name(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://presek:pass@localhost/presek_replica")
    monkeypatch.delenv("DATABASE_READ_REPLICA_URL", raising=False)
    assert "presek_replica" in resolve_primary_database_url()
