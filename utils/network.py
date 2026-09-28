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
