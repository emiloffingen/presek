import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.parametrize("env, expect_insert", [("test", False), ("production", True)])
def test_store_page_visit_skips_db_write_under_test_env(monkeypatch, env, expect_insert):
    from core import api_fast

    execute = AsyncMock()
    monkeypatch.setenv("ENV", env)
    with patch.object(api_fast, "db", MagicMock(async_execute=execute)):
        asyncio.run(api_fast._store_page_visit("v" * 64, "host", "/api/x", "mk", "", "u" * 64))

    assert execute.called is expect_insert
