import os
import secrets
import json
import logging
import datetime
import time
import re
import ipaddress
import html as _html
import urllib.request
import urllib.parse
import socket
from typing import Optional, List
from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from database import db_manager as db
from config import API_MAX_Q_LEN

log = logging.getLogger("presek")

_CLEAN_ARTIFACTS = [
    re.compile(r'Read\s+More\s*[»\>\-]*\s*$', re.I),
    re.compile(r'Прочитај\s+повеќе\s*$', re.I),
    re.compile(r'Continue\s+reading\s*$', re.I),
    re.compile(r'\[\s*&#\d+;\s*\]'),
    re.compile(r'\[\s*\.\.\.\s*\]'),
    re.compile(r'\s*&#8230;\s*$'),
    re.compile(r'\s*…\s*$'),
]

_PROXY_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_PROXY_MAX_BYTES = 10 * 1024 * 1024

def cleanAndDecode(text: str) -> str:
    if not text:
        return ''
    cleaned = _html.unescape(text)
    for rx in _CLEAN_ARTIFACTS:
        cleaned = rx.sub('', cleaned)
    cleaned = re.sub(r'^[⚪🟢🔴]\s*', '', cleaned)
    cleaned = re.sub(r'#[^\s#]+', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def _normalize_sync_list(values, limit=24):
    cleaned = []
    seen = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned

def _looks_macedonian_headline(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    cyrillic = sum(1 for ch in value if "\u0400" <= ch <= "\u04FF")
    latin = sum(1 for ch in value if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if cyrillic < 8:
        return False
    if latin == 0:
        return True
    return cyrillic >= (latin * 2)

def _preferred_cluster_headline(rows) -> str:
    preferred_mk = None
    fallback = ""
    for row in rows or []:
        title = cleanAndDecode(row.get("title") or "")
        if not title:
            continue
        if not fallback:
            fallback = title
        original_title = cleanAndDecode(row.get("original_title") or "")
        is_translated = bool(row.get("is_translated")) or (original_title and title != original_title)
        if is_translated and _looks_macedonian_headline(title):
            return title
        if preferred_mk is None and _looks_macedonian_headline(title):
            preferred_mk = title
    return preferred_mk or fallback or "Вест"

def _parse_ip_literal(value: str) -> str:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return ""

def _client_ip_for_request(request: Request) -> str:
    client_host = _parse_ip_literal(str(getattr(getattr(request, "client", None), "host", "") or ""))
    real_ip = _parse_ip_literal((request.headers.get("X-Real-IP") or "").split(",")[0].strip())
    if client_host in {"127.0.0.1", "::1"} and real_ip:
        return real_ip
    return client_host or "0.0.0.0"

def _source_admin_authorized(request: Request) -> bool:
    token = (request.headers.get("X-Admin-Token") or "").strip()
    expected = (os.environ.get("PRESEK_ADMIN_TOKEN") or "").strip()
    client_host = _client_ip_for_request(request)
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if not expected:
        return client_host in {"127.0.0.1", "::1"} and not forwarded_for
    if not token:
        return False
    return secrets.compare_digest(token, expected)

def _apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    return response

def _error_json(message: str, status_code: int, details=None):
    payload = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)

def _resolve_public_ips(candidate_url: str):
    parsed = urllib.parse.urlparse(candidate_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in {"localhost", "metadata.google.internal", "metadata.internal"}:
        raise ValueError("Blocked URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    safe = []
    for info in resolved:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
            if not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
                if ip not in safe: safe.append(ip)
        except ValueError: continue
    if not safe: raise PermissionError("Blocked URL")
    return safe

def _peer_ip(response):
    sock = None
    raw = getattr(response, "raw", None)
    if raw is not None:
        conn = getattr(raw, "connection", None) or getattr(raw, "_connection", None)
        if conn is not None: sock = getattr(conn, "sock", None)
    if sock is None: return None
    try: return sock.getpeername()[0]
    except Exception: return None

def _is_valid_focus_entity(name: str, entity_type: Optional[str]) -> bool:
    from local_nlp import is_valid_focus_entity
    return is_valid_focus_entity(name, entity_type)

def _extract_sync_token(request: Request) -> str:
    token = str(request.headers.get("X-Sync-Token") or "").strip()
    if token: return token
    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "): return auth[7:].strip()
    return ""

def _news_row_limit(page: int, page_size: int) -> int:
    return min(max((page + 1) * page_size * 12, 200), 2000)

def _normalize_suggestion_surface(value: str) -> str:
    return re.sub(r"[^a-z0-9_:-]+", "_", str(value or "").strip().lower())

def _normalize_suggestion_kind(value: str) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in {"topic", "source"} else ""

def _normalize_suggestion_event_type(value: str) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in {"impression", "follow", "dismiss"} else ""

def _safe_tracking_redirect_path(path: str) -> str:
    clean = str(path or "").strip()
    if not clean.startswith("/") or clean.startswith("//") or clean.startswith("/api/"): return "/briefing"
    if ".." in clean or "\\" in clean or ";" in clean: return "/briefing"
    _allowed = ("/briefing", "/cluster/", "/trending", "/archive", "/stati", "/subjekt/", "/tema/", "/izvori", "/status", "/stats", "/about", "/contact", "/privacy", "/debug/")
    if not any(clean.startswith(prefix) for prefix in _allowed) and clean != "/": return "/briefing"
    return clean

def _is_rate_limited_path(path: str) -> bool:
    clean = str(path or "").strip()
    if not clean.startswith("/api/"): return False
    return clean in {"/api/news", "/api/trending", "/api/intelligence/top-entities"}

def _rate_limit_error_payload() -> dict:
    return {"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}
