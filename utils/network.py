import ipaddress
import logging
import socket
import urllib.parse
from io import BytesIO
from typing import List, Optional

from PIL import Image

log = logging.getLogger("presek")


def _is_public_ip(ip: str) -> bool:
    """True when `ip` is a routable public address (safe to fetch from)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve_public_ips(candidate_url: str) -> List[str]:
    parsed = urllib.parse.urlparse(candidate_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in {
        "localhost",
        "metadata.google.internal",
        "metadata.internal",
    }:
        raise ValueError("Blocked URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Could not resolve hostname")

    safe = []
    for info in resolved:
        ip = info[4][0]
        if _is_public_ip(ip) and ip not in safe:
            safe.append(ip)
    if not safe:
        raise PermissionError("Blocked URL (Private/Reserved IP)")
    return safe


def _peer_is_public(response) -> bool:
    """Verify the *connected* peer is a public IP.

    The previous guard required the connected peer IP to be one of the
    DNS-resolved addresses. That rejects every CDN/proxy-fronted host (the TCP
    connection lands on a different anycast edge than DNS returned), which broke
    image downloads for most modern sites. We only need to ensure the request
    did not land on an internal/private address, so validate the peer directly.
    """
    ip = _peer_ip(response)
    if not ip:
        # Could not introspect the socket; fall back to the DNS allow-list check
        # at the call site rather than silently allowing.
        return False
    return _is_public_ip(ip)


def _peer_ip(response) -> Optional[str]:
    try:
        # httpx support
        extensions = getattr(response, "extensions", {})
        stream = extensions.get("network_stream")
        if stream:
            addr = stream.get_extra_info("server_addr")
            if addr:
                return addr[0]

        # requests support
        raw = getattr(response, "raw", None)
        if raw is not None:
            conn = getattr(raw, "connection", None) or getattr(raw, "_connection", None)
            if conn is not None:
                sock = getattr(conn, "sock", None)
                if sock is not None:
                    return sock.getpeername()[0]
    except Exception as e:
        log.debug(f"Failed to get peer IP: {e}")
    return None


class UnsafeFetchError(Exception):
    """A remote fetch was refused or failed; ``reason`` is a short machine-readable tag."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _pinned_request_parts(url: str, ip: str):
    """Rewrite ``url`` to connect to ``ip`` while keeping Host and TLS SNI on the hostname."""
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname or ""
    ip_host = f"[{ip}]" if ":" in ip else ip
    port_suffix = f":{parsed.port}" if parsed.port else ""
    pinned_url = urllib.parse.urlunsplit((parsed.scheme, ip_host + port_suffix, parsed.path or "/", parsed.query, ""))
    host_header = (f"[{hostname}]" if ":" in hostname else hostname) + port_suffix
    extensions = {"sni_hostname": hostname} if parsed.scheme == "https" else {}
    return pinned_url, host_header, extensions


async def fetch_public_bytes(
    url: str,
    *,
    max_bytes: int,
    headers: Optional[dict] = None,
    timeout: float = 8.0,
    max_redirects: int = 3,
    content_type_ok=None,
) -> bytes:
    """GET a public http(s) URL without ever touching private addresses.

    Each hop (including redirects) is resolved up front, rejected if it maps to a
    private/reserved address, and then connected to by IP so a second DNS answer
    (rebinding) cannot redirect the request. Redirects are followed manually so
    every Location is re-validated before any request is sent to it.
    Raises ``UnsafeFetchError`` with a reason tag on any refusal or failure.
    """
    import asyncio

    import httpx

    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            parsed = urllib.parse.urlsplit(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise UnsafeFetchError("invalid_scheme")
            try:
                safe_ips = await asyncio.to_thread(_resolve_public_ips, current)
            except Exception:
                raise UnsafeFetchError("security_ssrf_block")

            pinned_url, host_header, extensions = _pinned_request_parts(current, safe_ips[0])
            request_headers = dict(headers or {})
            request_headers["Host"] = host_header
            request = client.build_request("GET", pinned_url, headers=request_headers, extensions=extensions)
            try:
                response = await client.send(request, stream=True)
            except httpx.HTTPError as exc:
                raise UnsafeFetchError(f"fetch_error:{type(exc).__name__}")
            try:
                peer = _peer_ip(response)
                if peer and not _is_public_ip(peer):
                    raise UnsafeFetchError("security_ssrf_block")

                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeFetchError(f"http_{response.status_code}")
                    current = urllib.parse.urljoin(current, location)
                    continue

                if response.status_code != 200:
                    raise UnsafeFetchError(f"http_{response.status_code}")

                if content_type_ok is not None and not content_type_ok(str(response.headers.get("Content-Type", ""))):
                    raise UnsafeFetchError("invalid_content_type")

                data = b""
                async for chunk in response.aiter_bytes(chunk_size=16384):
                    data += chunk
                    if len(data) > max_bytes:
                        raise UnsafeFetchError("too_large")
                return data
            finally:
                await response.aclose()

    raise UnsafeFetchError("too_many_redirects")


async def get_dominant_color(url: str) -> str:
    """Extracts the dominant hex color from an image URL (Asynchronous)."""
    if not url:
        return ""

    internal_proxy_markers = [
        "/api/proxy",
        "presek.live/proxy",
        "localhost:5001/proxy",
        "api:5001/proxy",
    ]
    if any(marker in url for marker in internal_proxy_markers):
        log.warning(f"[utils] color extraction blocked for recursive/internal URL: {url}")
        return ""

    if not url.startswith("http"):
        return ""

    try:
        import httpx

        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, max_redirects=2) as client:
            try:
                _resolve_public_ips(url)
            except Exception as e:
                log.debug(f"Failed to resolve public IPs for {url}: {e}")
                return ""

            async with client.stream("GET", url, headers={"User-Agent": "PresekColorBot/1.0"}) as response:
                if response.status_code != 200:
                    return ""

                if not _peer_is_public(response):
                    log.warning(f"[utils] color extraction blocked: private/unresolvable peer for {url}")
                    return ""

                content = await response.aread()

        img = Image.open(BytesIO(content))
        img = img.convert("RGB")
        img.thumbnail((60, 60))

        colors = img.getcolors(3600)
        if not colors:
            return ""

        def is_usable(rgb):
            r, g, b = rgb
            if r > 245 and g > 245 and b > 245:
                return False
            if r < 15 and g < 15 and b < 15:
                return False
            avg = (r + g + b) / 3
            if abs(r - avg) < 12 and abs(g - avg) < 12 and abs(b - avg) < 12:
                return False
            return True

        sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
        usable = [c for c in sorted_colors if is_usable(c[1])]
        dominant = usable[0][1] if usable else sorted_colors[0][1]

        return "#{:02x}{:02x}{:02x}".format(*dominant)
    except Exception as e:
        log.debug(f"[utils] color extraction failed for {url}: {e}")
        return ""
