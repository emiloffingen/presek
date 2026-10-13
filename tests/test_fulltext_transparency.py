"""Tests for full-text transparency: payload gating, config flags, robots."""

import asyncio
import importlib

import pytest

import core.crawler as crawler
import core.http_pool as http_pool
import utils.network as network


def _article():
    return {
        "id": 42,
        "cluster_id": "c1",
        "source": "Test Source",
        "link": "https://example.mk/a",
        "title": "Naslov",
        "description": "Opis",
        "full_content": "Целосен текст на статијата.",
        "country": "MK",
    }


def test_full_content_excluded_by_default():
    from routes.news import _public_article_payload

    out = _public_article_payload(_article(), lang="mk", include_full_content=False)
    assert "full_content" not in out


def test_full_content_included_when_requested():
    from routes.news import _public_article_payload

    out = _public_article_payload(_article(), lang="mk", include_full_content=True)
    assert out.get("full_content") == "Целосен текст на статијата."


def test_config_defaults_fulltext_enabled(monkeypatch):
    monkeypatch.delenv("FULLTEXT_ENABLED", raising=False)
    monkeypatch.delenv("FULLTEXT_MAX_CHARS", raising=False)
    monkeypatch.delenv("MK_ONLY", raising=False)
    import core.config as config

    importlib.reload(config)
    assert config.FULLTEXT_ENABLED is True
    assert config.FULLTEXT_MAX_CHARS == 20000
    assert config.MK_ONLY is True
    assert "PresekBot" in config.BOT_USER_AGENT


class _FakeResp:
    def __init__(self, text, status=200):
        self.status_code = status
        self.text = text

    async def aread(self):
        return self.text.encode()


class _FakeStream:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


_ROBOTS = {}


class _FakeClient:
    is_closed = False

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, **kwargs):
        return _FakeStream(_ROBOTS[url])


@pytest.fixture
def fake_http(monkeypatch):
    crawler._ROBOTS_CACHE.clear()
    http_pool._async_clients.clear()
    monkeypatch.setattr(http_pool.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(crawler, "_resolve_public_ips", lambda url: {"1.2.3.4"})
    monkeypatch.setattr(network, "_peer_ip", lambda resp: "1.2.3.4")
    yield
    crawler._ROBOTS_CACHE.clear()
    http_pool._async_clients.clear()


def test_robots_disallow(fake_http):
    _ROBOTS.clear()
    _ROBOTS["https://example.mk/robots.txt"] = _FakeResp("User-agent: *\nDisallow: /private\n")
    assert asyncio.run(crawler._robots_allows("https://example.mk/private/story")) is False
    assert asyncio.run(crawler._robots_allows("https://example.mk/public/story")) is True


def test_robots_missing_fails_open(fake_http):
    _ROBOTS.clear()
    _ROBOTS["https://example.mk/robots.txt"] = _FakeResp("not found", status=404)
    assert asyncio.run(crawler._robots_allows("https://example.mk/anything")) is True
