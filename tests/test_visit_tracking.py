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


def _scope(headers, client_host):
    return {
        "type": "http",
        "method": "POST",
        "path": "/api/stats/beacon",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345),
        "query_string": b"",
    }


def test_visit_ip_ignores_spoofed_forwarded_for_behind_tunnel():
    from starlette.requests import Request

    from core import api_fast

    # cloudflared connects from loopback; only CF-Connecting-IP is trustworthy there.
    tunneled = Request(_scope({"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": "1.2.3.4"}, "127.0.0.1"))
    assert api_fast._visit_client_ip(tunneled) == "203.0.113.7"

    # A direct peer cannot pick its own visitor identity with X-Forwarded-For.
    direct = Request(_scope({"X-Forwarded-For": "1.2.3.4"}, "198.51.100.4"))
    assert api_fast._visit_client_ip(direct) == "198.51.100.4"


def test_beacon_is_not_exempt_from_rate_limiting():
    from core import api_fast  # noqa: F401 - importing registers the routes
    from core.limiter import limiter

    if limiter is None:
        pytest.skip("slowapi not installed")
    assert "core.api_fast.visitor_beacon" not in limiter._exempt_routes
