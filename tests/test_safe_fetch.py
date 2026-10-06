"""SSRF guard for outbound image fetches (utils.network.fetch_public_bytes)."""

import asyncio
from unittest.mock import patch

import httpx
import pytest

import utils.network as network
from utils.network import UnsafeFetchError, fetch_public_bytes

DNS = {
    "img.example": ["93.184.216.34"],
    "cdn.example": ["151.101.1.1"],
    "rebind.example": ["127.0.0.1"],
    "meta.example": ["169.254.169.254"],
}


@pytest.mark.parametrize(
    "ip",
    [
        "100.77.135.12",  # Tailscale / CGNAT (100.64.0.0/10)
        "100.64.0.1",
        "::ffff:127.0.0.1",
        "::ffff:100.77.135.12",
        "169.254.169.254",
        "10.0.0.1",
        "224.0.0.1",
        "not-an-ip",
    ],
)
def test_non_public_addresses_are_rejected(ip):
    assert network._is_public_ip(ip) is False


@pytest.mark.parametrize("ip", ["93.184.216.34", "151.101.1.1", "2606:4700:4700::1111"])
def test_public_addresses_are_accepted(ip):
    assert network._is_public_ip(ip) is True


def _fake_resolve(url):
    host = httpx.URL(url).host
    if host.replace(".", "").isdigit():
        ips = [host]
    else:
        ips = DNS.get(host, [])
    public = [ip for ip in ips if network._is_public_ip(ip)]
    if not public:
        raise PermissionError("Blocked URL (Private/Reserved IP)")
    return public


def _run(url, handler, **kwargs):
    sent = []

    def recording_handler(request):
        sent.append(request)
        return handler(request)

    real_client = httpx.AsyncClient

    def client_factory(*args, **kw):
        kw["transport"] = httpx.MockTransport(recording_handler)
        return real_client(*args, **kw)

    with (
        patch.object(network, "_resolve_public_ips", side_effect=_fake_resolve),
        patch("httpx.AsyncClient", side_effect=client_factory),
    ):
        try:
            result = asyncio.run(fetch_public_bytes(url, max_bytes=1024, **kwargs))
        except UnsafeFetchError as exc:
            return exc, sent
    return result, sent


def _image(body=b"img"):
    return httpx.Response(200, headers={"Content-Type": "image/png"}, content=body)


def test_connects_to_pinned_ip_with_original_host_and_sni():
    result, sent = _run("https://img.example/a.png?x=1", lambda r: _image())

    assert result == b"img"
    assert len(sent) == 1
    assert sent[0].url.host == "93.184.216.34"
    assert sent[0].url.raw_path == b"/a.png?x=1"
    assert sent[0].headers["host"] == "img.example"
    assert sent[0].extensions["sni_hostname"] == "img.example"


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1:5001/api/admin/dashboard",
        "http://169.254.169.254/latest/meta-data",
        "http://rebind.example/",
        "http://meta.example/",
        "gopher://img.example/",
    ],
)
def test_redirect_to_private_target_is_refused_before_sending(location):
    def handler(request):
        return httpx.Response(302, headers={"Location": location})

    result, sent = _run("https://img.example/a.png", handler)

    assert isinstance(result, UnsafeFetchError)
    assert result.reason in {"security_ssrf_block", "invalid_scheme"}
    # Only the first (public) hop was ever sent.
    assert len(sent) == 1


def test_public_redirect_is_followed_and_re_resolved():
    def handler(request):
        if request.headers["host"] == "img.example":
            return httpx.Response(301, headers={"Location": "https://cdn.example/b.png"})
        return _image(b"cdn")

    result, sent = _run("https://img.example/a.png", handler)

    assert result == b"cdn"
    assert [r.url.host for r in sent] == ["93.184.216.34", "151.101.1.1"]


def test_redirect_loop_is_capped():
    result, sent = _run(
        "https://img.example/a.png",
        lambda r: httpx.Response(302, headers={"Location": "/again"}),
        max_redirects=2,
    )
    assert isinstance(result, UnsafeFetchError)
    assert result.reason == "too_many_redirects"
    assert len(sent) == 3


def test_private_initial_target_never_sent():
    result, sent = _run("http://rebind.example/a.png", lambda r: _image())
    assert isinstance(result, UnsafeFetchError)
    assert result.reason == "security_ssrf_block"
    assert sent == []


def test_content_type_and_size_limits():
    result, _ = _run(
        "https://img.example/a.png",
        lambda r: httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<x>"),
        content_type_ok=lambda ct: ct.startswith("image/"),
    )
    assert result.reason == "invalid_content_type"

    result, _ = _run("https://img.example/a.png", lambda r: _image(b"x" * 2048))
    assert result.reason == "too_large"
