import os
import secrets
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import asyncio
import json
import logging
import datetime
import time
import re
from typing import Optional, List
from collections import defaultdict
import urllib.request
import urllib.parse
import socket
import ipaddress
from pathlib import Path

import html as _html
import requests

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time, 
    cached_response, set_cache, delete_cache, is_balanced, assess_cluster_synthesis_freshness,
    annotate_cluster_articles, score_cluster_for_homepage, build_read_next_clusters,
    build_source_reputation_rows, build_editor_analytics_payload,
    event_stream, check_rate_limit, record_runtime_event,
)
from ai_engine import PROVIDERS, _call_ai_async, clean_json_response
from prompts import SYNTHESIS_SYSTEM_PROMPT
from config import (
    BREAKING_SCORE_THRESHOLD,
    API_MAX_PAGE,
    API_MAX_Q_LEN,
    SOURCE_CREDIBILITY,
    DEFAULT_CREDIBILITY,
    validate_required_env,
)
from local_nlp import (
    answer_cluster_question_locally,
    generate_daily_brief_fallback,
    normalize_tag_name,
    filter_cluster_tags,
    is_valid_focus_entity,
    build_citation_snippet,
    build_structured_answer_sections,
    ENTITY_NOISE_WORDS,
)
from health import _probe_database, _probe_redis, get_source_statuses, reset_source_policy
from api_helpers import (
    normalize_perspectives as _parse_perspectives_blob,
    default_related_questions as _default_related_questions,
    related_questions_from_context as _related_questions_from_context,
    text_terms as _text_terms,
    rank_cluster_citations as _rank_cluster_citations,
    normalize_server_delivery_subscription as _normalize_server_delivery_subscription,
)

log = logging.getLogger("presek")
log.setLevel(logging.INFO)

_CLEAN_ARTIFACTS = [
    re.compile(r'Read\s+More\s*[»\>\-]*\s*$', re.I),
    re.compile(r'Прочитај\s+повеќе\s*$', re.I),
    re.compile(r'Continue\s+reading\s*$', re.I),
    re.compile(r'\[\s*&#\d+;\s*\]'),
    re.compile(r'\[\s*\.\.\.\s*\]'),
    re.compile(r'\s*&#8230;\s*$'),
    re.compile(r'\s*…\s*$'),
]

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

validate_required_env()
app = FastAPI(title="Presek API 6.0", version="6.0.0")
_start_time = datetime.datetime.now(datetime.timezone.utc)
_APP_ROOT = Path(__file__).resolve().parent
_STATIC_ROOT = _APP_ROOT / "static"
_PROXY_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_PROXY_MAX_BYTES = 10 * 1024 * 1024
_WMO_ICON = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌦️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "❄️", 73: "❄️", 75: "❄️", 77: "❄️",
    80: "🌦️", 81: "🌦️", 82: "🌦️",
    85: "❄️", 86: "❄️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}
_public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live").rstrip("/")
_default_cors_origins = [
    _public_site_url,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4321",
    "http://127.0.0.1:4321",
]
_configured_cors_origins = [
    origin.rstrip("/")
    for origin in (o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(","))
    if origin and origin != "*"
]
_cors_origins = _configured_cors_origins or _default_cors_origins

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


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


def _normalize_recent_clusters(items):
    rows = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        cluster_id = str(item.get("cluster_id") or "").strip()
        if not cluster_id or cluster_id in seen:
            continue
        seen.add(cluster_id)
        rows.append({
            "cluster_id": cluster_id,
            "title": str(item.get("title") or "").strip(),
            "category": str(item.get("category") or "").strip(),
            "topic": str(item.get("topic") or "").strip(),
            "primarySource": str(item.get("primarySource") or "").strip(),
            "sources": _normalize_sync_list(item.get("sources") or [], limit=8),
            "tags": _normalize_sync_list(item.get("tags") or [], limit=10),
            "viewedAt": str(item.get("viewedAt") or "").strip(),
        })
        if len(rows) >= 24:
            break
    return rows


def _looks_macedonian_headline(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False

    cyrillic = sum(1 for ch in value if "\u0400" <= ch <= "\u04FF")
    latin = sum(1 for ch in value if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))

    # Macedonian headlines should read primarily in Cyrillic. Allow a few
    # Latin brand names or acronyms, but reject mixed or fully Latin titles.
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


def _normalize_delivery_preferences(prefs):
    prefs = prefs or {}
    return {
        "morningBriefing": prefs.get("morningBriefing") is not False,
        "breakingAlerts": prefs.get("breakingAlerts") is not False,
        "browserPermission": str(prefs.get("browserPermission") or "default").strip() or "default",
    }


def _normalize_synced_profile(payload):
    payload = payload or {}
    return {
        "followedTopics": _normalize_sync_list(payload.get("followedTopics") or [], limit=12),
        "followedSources": _normalize_sync_list(payload.get("followedSources") or [], limit=12),
        "recentClusters": _normalize_recent_clusters(payload.get("recentClusters") or []),
        "deliveryPreferences": _normalize_delivery_preferences(payload.get("deliveryPreferences") or {}),
    }


def _merge_synced_profiles(left, right):
    left = _normalize_synced_profile(left)
    right = _normalize_synced_profile(right)

    merged_recent = _normalize_recent_clusters(
        sorted(
            left["recentClusters"] + right["recentClusters"],
            key=lambda item: str(item.get("viewedAt") or ""),
            reverse=True,
        )
    )

    return {
        "followedTopics": _normalize_sync_list(left["followedTopics"] + right["followedTopics"], limit=12),
        "followedSources": _normalize_sync_list(left["followedSources"] + right["followedSources"], limit=12),
        "recentClusters": merged_recent,
        "deliveryPreferences": {
            **left["deliveryPreferences"],
            **right["deliveryPreferences"],
        },
    }


def _default_server_delivery_subscription():
    return _normalize_server_delivery_subscription({})


def _normalize_server_delivery_row(row):
    if not row:
        return _default_server_delivery_subscription()
    return _normalize_server_delivery_subscription({
        "channel": row.get("channel"),
        "target": row.get("target"),
        "morningBriefing": row.get("morning_briefing"),
        "weeklyDigest": row.get("weekly_digest"),
        "breakingTopics": row.get("breaking_topics"),
        "breakingSources": row.get("breaking_sources"),
        "isActive": row.get("is_active"),
    })


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
    if not clean.startswith("/"):
        return "/briefing"
    if clean.startswith("//") or clean.startswith("/api/"):
        return "/briefing"
    return clean


def _is_rate_limited_path(path: str) -> bool:
    clean = str(path or "").strip()
    if not clean.startswith("/api/"):
        return False
    # Rate limit these expensive endpoints
    if clean in {"/api/chat_cluster", "/api/chat/stream", "/api/news", "/api/trending", "/api/intelligence/top-entities"}:
        return True
    return bool(re.match(r"^/api/cluster/[a-f0-9]{6,64}/ask$", clean))



def _rate_limit_error_payload() -> dict:
    return {"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}


def _parse_ip_literal(value: str) -> str:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return ""


def _extract_sync_token(request: Request) -> str:
    token = str(request.headers.get("X-Sync-Token") or "").strip()
    if token:
        return token

    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _row_int_value(row, key: str = "count", default: int = 0) -> int:
    if row is None:
        return default
    if isinstance(row, dict):
        value = row.get(key)
        if value is None:
            for candidate in row.values():
                if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                    value = candidate
                    break
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(row, (list, tuple)) and row:
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return default
    return default


def _news_row_limit(page: int, page_size: int) -> int:
    # Fetch enough article rows to rank cluster pages beyond the first page
    # instead of truncating every request to the same shallow window.
    return min(max((page + 1) * page_size * 12, 200), 5000)


def _client_ip_for_request(request: Request) -> str:
    client_host = _parse_ip_literal(str(getattr(getattr(request, "client", None), "host", "") or ""))
    real_ip = _parse_ip_literal((request.headers.get("X-Real-IP") or "").split(",")[0].strip())

    # Only trust proxy-provided client IPs when the direct peer is our local reverse proxy.
    if client_host in {"127.0.0.1", "::1"} and real_ip:
        return real_ip
    if client_host:
        return client_host
    return "0.0.0.0"


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


def _source_admin_authorized(request: Request) -> bool:
    token = (request.headers.get("X-Admin-Token") or "").strip()
    expected = (os.environ.get("PRESEK_ADMIN_TOKEN") or "").strip()
    client_host = str(getattr(getattr(request, "client", None), "host", "") or "").strip()
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()

    if expected and token and secrets.compare_digest(token, expected):
        return True
    if client_host in {"127.0.0.1", "::1"} and not forwarded_for:
        return True
    return False


def _error_json(message: str, status_code: int, details=None):
    payload = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def _resolve_public_ips(candidate_url: str):
    parsed = urllib.parse.urlparse(candidate_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Blocked URL")
    if hostname in {"localhost", "metadata.google.internal", "metadata.internal"}:
        raise ValueError("Blocked URL")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolved_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    safe_ips = []
    for info in resolved_infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
                or addr.is_unspecified
            ):
                continue
        except ValueError:
            continue
        if ip not in safe_ips:
            safe_ips.append(ip)
    if not safe_ips:
        raise PermissionError("Blocked URL (Private/Reserved IP)")
    return safe_ips


def _peer_ip(response):
    sock = None
    raw = getattr(response, "raw", None)
    if raw is not None:
        connection = getattr(raw, "connection", None) or getattr(raw, "_connection", None)
        if connection is not None:
            sock = getattr(connection, "sock", None)
    if sock is None:
        return None
    try:
        return sock.getpeername()[0]
    except Exception:
        return None

def _is_valid_focus_entity(name: str, entity_type: Optional[str]) -> bool:
    return is_valid_focus_entity(name, entity_type)


def _build_cluster_answer_fallback(question: str, articles, synthesis: str = "", perspectives=None) -> dict:
    articles = [dict(article) if not isinstance(article, dict) else article for article in (articles or [])]
    category = articles[0].get("category") if articles else None
    perspectives = _parse_perspectives_blob(perspectives or [])
    local_answer = None

    try:
        local_answer = answer_cluster_question_locally(
            question,
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] local helper failed, using minimal fallback: {e}")

    if not local_answer and articles:
        lead = articles[0]
        lead_title = str(lead.get("title") or "Оваа приказна")
        lead_source = str(lead.get("source") or "Извор").strip()
        local_answer = {
            "answer": f"Најважното во овој момент е: {lead_title}. Водечкиот достапен извор во овој кластер е {lead_source}.",
            "citations": articles[:2],
            "related_questions": _default_related_questions(question, category),
            "confidence": "low",
        }

    sections = {
        "confirmed_points": [],
        "unclear_points": [],
        "source_differences": "",
    }
    try:
        sections = build_structured_answer_sections(
            local_answer["answer"] if local_answer else "",
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] section builder failed during fallback: {e}")

    citations = []
    try:
        citations = _rank_cluster_citations(
            question,
            local_answer["answer"] if local_answer else "",
            articles,
            [],
        )
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] citation ranking failed during fallback: {e}")
        citations = [
            {
                "source": article.get("source"),
                "title": article.get("title"),
                "link": article.get("link"),
                "created_at": article.get("created_at"),
                "snippet": build_citation_snippet(article),
            }
            for article in articles[:2]
        ]

    return {
        "status": "success",
        "answer": (local_answer or {}).get("answer", "Во моментов системот не може да даде подетален одговор."),
        "citations": citations,
        "related_questions": (local_answer or {}).get("related_questions") or _related_questions_from_context(
            question,
            category,
            has_perspectives=bool(perspectives),
            has_multiple_sources=len(articles) >= 2,
            has_unclear_points=bool(sections.get("unclear_points")),
        ),
        "confidence": (local_answer or {}).get("confidence", "low"),
        "confirmed_points": sections.get("confirmed_points", [])[:3],
        "unclear_points": sections.get("unclear_points", [])[:2],
        "source_differences": sections.get("source_differences", ""),
        "generated_locally": True,
    }


async def _build_cluster_answer_payload(cluster_id: str, question: str) -> dict:
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    if len(question) > API_MAX_Q_LEN:
        raise HTTPException(status_code=400, detail="Question is too long")

    articles = []
    synthesis = ""
    perspectives = []
    try:
        articles = db.execute(
            """
            SELECT title, description, source, link, created_at, category
            FROM articles
            WHERE cluster_id = %s
            ORDER BY created_at DESC
            LIMIT 8
            """,
            (cluster_id,)
        )
        articles = [dict(article) if not isinstance(article, dict) else article for article in articles]
        if not articles:
            raise HTTPException(status_code=404, detail="Cluster not found")

        summary_row = db.execute_one(
            "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
            (cluster_id,)
        )
        synthesis = (summary_row or {}).get("summary") or ""
        perspectives = _parse_perspectives_blob((summary_row or {}).get("perspectives"))

        try:
            local_answer = answer_cluster_question_locally(question, articles, synthesis=synthesis, perspectives=perspectives)
        except Exception as e:
            log.warning(f"[fastapi cluster_answer] local answer generation failed for {cluster_id}: {e}", exc_info=True)
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
        if local_answer:
            try:
                sections = build_structured_answer_sections(
                    local_answer["answer"],
                    articles,
                    synthesis=synthesis,
                    perspectives=perspectives,
                )
            except Exception as e:
                log.warning(f"[fastapi cluster_answer] section building failed for {cluster_id}: {e}", exc_info=True)
                return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
            return {
                "status": "success",
                "answer": local_answer.get("answer", ""),
                "citations": _safe_rank_cluster_citations(question, local_answer.get("answer", ""), articles, [])[:3],
                "related_questions": list(local_answer.get("related_questions") or [])[:3],
                "confidence": local_answer.get("confidence", "medium"),
                "confirmed_points": sections["confirmed_points"],
                "unclear_points": sections["unclear_points"],
                "source_differences": sections["source_differences"],
                "generated_locally": True,
            }

        article_context = []
        for idx, article in enumerate(articles, start=1):
            article_context.append(
                f"[{idx}] Извор: {article['source']}\n"
                f"Наслов: {article['title']}\n"
                f"Опис: {(article.get('description') or '').strip()}\n"
            )

        perspective_context = "\n".join(
            f"- {item['angle']}: {item['content']}" for item in perspectives[:4]
        )

        prompt = (
            "Контекст за еден новински кластер:\n\n"
            f"Системско резиме:\n{synthesis or 'Нема достапно резиме.'}\n\n"
            f"Перспективи:\n{perspective_context or 'Нема издвоени перспективи.'}\n\n"
            "Извори:\n"
            + "\n".join(article_context)
            + "\n"
            f"Прашање од корисник: {question}\n\n"
            "Одговори само врз основа на контекстот погоре. Ако нешто не е потврдено или недостига, кажи го тоа јасно. "
            "Врати JSON со полиња: "
            "{\"answer\":\"...\",\"confirmed_points\":[\"...\"],\"unclear_points\":[\"...\"],\"source_differences\":\"...\",\"citation_numbers\":[1,2],\"related_questions\":[\"...\",\"...\",\"...\"],\"confidence\":\"high|medium|low\"}. "
            "Во citation_numbers вклучи само броеви од листата на извори што директно го поддржуваат одговорот. "
            "Одговорот мора да биде на македонски."
        )

        system = (
            "You are a professional editorial assistant. You must synthesize the provided text into natural, flowing sentences. "
            "CRITICAL: NEVER output raw metadata, author names, publication dates, or category tags (e.g., do not output strings like 'Александра Спасеска 07.04.2026 / 16:08 Хроника'). "
            "Do not repeat the same sentence twice. Extract only the facts. "
            "Ти си новинарски асистент за Пресек. Не измислувај факти. "
            "Ако контекстот не е доволен, кажи што не е јасно. Биди прецизен и концизен."
        )

        try:
            response_text, provider = await _call_ai_async(
                prompt,
                system,
                task_type="chat",
                max_tokens=700,
                json_mode=True,
            )
        except Exception as e:
            log.warning(f"[fastapi cluster_answer] AI call failed for {cluster_id}: {e}", exc_info=True)
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)

        if not response_text:
            record_runtime_event("chat_path", mode="local_fallback", surface="cluster_answer")
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
        record_runtime_event("chat_path", mode=provider or "unknown", surface="cluster_answer")

        try:
            parsed = clean_json_response(response_text)
        except Exception as e:
            log.warning(f"[fastapi cluster_answer] AI response cleaning failed for {cluster_id}: {e}", exc_info=True)
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
        if isinstance(parsed, dict):
            answer = str(parsed.get("answer") or "").strip()
            confirmed_points = [str(item).strip() for item in parsed.get("confirmed_points") or [] if str(item).strip()]
            unclear_points = [str(item).strip() for item in parsed.get("unclear_points") or [] if str(item).strip()]
            source_differences = str(parsed.get("source_differences") or "").strip()
            citation_numbers = parsed.get("citation_numbers") or []
            related_questions = parsed.get("related_questions") or []
            confidence = str(parsed.get("confidence") or "medium").strip().lower()
        else:
            answer = str(parsed).strip()
            confirmed_points = []
            unclear_points = []
            source_differences = ""
            citation_numbers = [1, 2]
            related_questions = []
            confidence = "medium"

        citations = _safe_rank_cluster_citations(question, answer, articles, citation_numbers)
        try:
            sections = build_structured_answer_sections(
                answer,
                articles,
                synthesis=synthesis,
                perspectives=perspectives,
            )
        except Exception as e:
            log.warning(f"[fastapi cluster_answer] final section building failed for {cluster_id}: {e}", exc_info=True)
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
        if not confirmed_points:
            confirmed_points = sections["confirmed_points"]
        if not unclear_points:
            unclear_points = sections["unclear_points"]
        if not source_differences:
            source_differences = sections["source_differences"]

        clean_related = []
        for item in related_questions:
            text = str(item).strip()
            if text and text not in clean_related and text != question:
                clean_related.append(text)

        if not clean_related:
            clean_related = _related_questions_from_context(
                question,
                articles[0].get("category"),
                has_perspectives=bool(perspectives),
                has_multiple_sources=len(articles) >= 2,
                has_unclear_points=bool(unclear_points),
            )

        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"

        return {
            "status": "success",
            "answer": answer,
            "citations": citations[:3],
            "related_questions": clean_related[:3],
            "confidence": confidence,
            "confirmed_points": confirmed_points[:3],
            "unclear_points": unclear_points[:2],
            "source_differences": source_differences,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[fastapi cluster_answer] unexpected error for {cluster_id}: {e}", exc_info=True)
        return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)


def _fallback_citations(articles) -> list[dict]:
    return [
        {
            "source": article.get("source"),
            "title": article.get("title"),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "snippet": build_citation_snippet(article),
        }
        for article in (articles or [])[:2]
    ]


def _safe_rank_cluster_citations(question: str, answer: str, articles, citation_numbers) -> list[dict]:
    try:
        return _rank_cluster_citations(question, answer, articles, citation_numbers)
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] citation ranking failed: {e}", exc_info=True)
        return _fallback_citations(articles)


@app.middleware("http")
async def apply_runtime_policies(request: Request, call_next):
    start_time = time.time()
    if _is_rate_limited_path(request.url.path):
        client_host = _client_ip_for_request(request)

        if not check_rate_limit(client_host):
            return _apply_security_headers(JSONResponse(status_code=429, content=_rate_limit_error_payload()))

    response = await call_next(request)
    duration = time.time() - start_time
    log.info(f"API {request.method} {request.url.path} took {duration:.4f}s")
    return _apply_security_headers(response)

@app.get("/api/health")
async def health(request: Request):
    db_status = _probe_database()
    redis_status = _probe_redis()
    uptime_seconds = int((datetime.datetime.now(datetime.timezone.utc) - _start_time).total_seconds())
    overall = "ok" if (db_status["ok"] and redis_status["ok"]) else "degraded"
    payload = {
        "status": overall,
        "version": "6.0.0-async",
        "uptime_seconds": uptime_seconds,
        "database": {
            "ok": db_status["ok"],
            "article_count": db_status.get("article_count", 0),
            "size_mb": db_status.get("size_mb", 0.0),
        },
        "redis": {
            "ok": redis_status["ok"],
        },
    }
    if _source_admin_authorized(request):
        if db_status.get("error"):
            payload["database"]["error"] = db_status["error"]
        if redis_status.get("url"):
            payload["redis"]["url"] = redis_status["url"]
        if redis_status.get("error"):
            payload["redis"]["error"] = redis_status["error"]
    return payload


@app.get("/sw.js")
async def serve_sw():
    return FileResponse("sw.js", media_type="application/javascript")


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(os.path.join("static", "manifest.json"), media_type="application/manifest+json")


@app.get("/robots.txt")
async def robots_txt():
    return Response("User-agent: *\nDisallow: /api/\nAllow: /\n\nSitemap: https://presek.live/sitemap-index.xml\n", media_type="text/plain")


@app.get("/og/cluster/{cluster_id}.svg")
async def og_cluster_image(cluster_id: str):
    if not cluster_id or not re.match(r"^[a-f0-9]{6,64}$", cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster")

    rows = db.execute(
        "SELECT title, original_title, is_translated FROM articles WHERE cluster_id = %s ORDER BY created_at DESC",
        (cluster_id,),
    )
    if not isinstance(rows, list):
        lead_row = db.execute_one(
            "SELECT title, original_title, is_translated FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 1",
            (cluster_id,),
        )
        rows = [lead_row] if lead_row else []
    count_row = db.execute_one("SELECT COUNT(*) FROM articles WHERE cluster_id = %s", (cluster_id,))

    title = _preferred_cluster_headline(rows)
    import html
    title = html.unescape(title)
    count = _row_int_value(count_row, default=1)
    safe_title = html.escape(title)
    if len(safe_title) > 65:
        line1 = safe_title[:65]
        line2 = safe_title[65:130] + ("..." if len(safe_title) > 130 else "")
    else:
        line1 = safe_title
        line2 = ""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a1a"/>
  <rect width="1200" height="10" y="0" fill="#E63946"/>
  <text x="100" y="120" font-family="serif" font-size="32" font-weight="800" fill="#E63946" letter-spacing="2">ПРЕСЕК АНАЛИЗА</text>
  <text x="100" y="240" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line1}</text>
  <text x="100" y="320" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line2}</text>
  <text x="100" y="520" font-family="sans-serif" font-size="28" fill="#aaaaaa">{count} извори анализирани во овој кластер</text>
  <text x="1100" y="560" font-family="serif" font-size="48" font-weight="bold" fill="#E63946" text-anchor="end">пресек.мк</text>
</svg>"""
    return Response(svg, media_type="image/svg+xml")


@app.get("/og-image.svg")
async def og_image():
    row = db.execute_one("SELECT COUNT(*) FROM articles")
    count = _row_int_value(row, default=0)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a2e"/>
  <text x="600" y="280" font-family="sans-serif" font-size="72" font-weight="bold" fill="#ffffff" text-anchor="middle">Пресек</text>
  <text x="600" y="380" font-family="sans-serif" font-size="36" fill="#aaaaaa" text-anchor="middle">{count} статии индексирани</text>
</svg>"""
    return Response(svg, media_type="image/svg+xml")


@app.get("/static/{asset_path:path}")
async def serve_static_asset(asset_path: str):
    clean = str(asset_path or "").strip().lstrip("/")
    if not clean:
        raise HTTPException(status_code=404, detail="Not found")

    candidate = (_STATIC_ROOT / clean).resolve()
    try:
        candidate.relative_to(_STATIC_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Blocked path")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(candidate)


@app.post("/api/profile/sync/init")
async def init_profile_sync():
    token = secrets.token_urlsafe(18)
    empty_profile = _normalize_synced_profile({})
    db.execute(
        "INSERT INTO synced_reader_profiles (sync_token, profile_data) VALUES (%s, %s::jsonb)",
        (token, json.dumps(empty_profile)),
        fetch=False,
    )
    return {
        "status": "success",
        "token": token,
        "profile": empty_profile,
    }


@app.get("/api/profile/sync")
async def get_profile_sync(request: Request):
    token = _extract_sync_token(request)
    if not token or len(token) < 12 or len(token) > 128:
        raise HTTPException(status_code=400, detail="Missing sync token")
    row = db.execute_one(
        "SELECT profile_data, updated_at FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Synced profile not found")
    return {
        "status": "success",
        "profile": _normalize_synced_profile(row.get("profile_data") or {}),
        "updated_at": row.get("updated_at"),
    }


@app.post("/api/profile/sync")
async def save_profile_sync(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing sync token")

    incoming = _normalize_synced_profile(payload.get("profile") or {})
    existing = db.execute_one(
        "SELECT profile_data FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Synced profile not found")

    merged = _merge_synced_profiles(existing.get("profile_data") or {}, incoming)
    db.execute(
        "UPDATE synced_reader_profiles SET profile_data = %s::jsonb, updated_at = NOW() WHERE sync_token = %s",
        (json.dumps(merged), token),
        fetch=False,
    )
    return {
        "status": "success",
        "profile": merged,
    }


@app.get("/api/profile/delivery")
async def get_profile_delivery(request: Request):
    token = _extract_sync_token(request)
    if not token or len(token) < 12 or len(token) > 128:
        raise HTTPException(status_code=400, detail="Missing sync token")
    profile = db.execute_one(
        "SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Synced profile not found")

    row = db.execute_one(
        "SELECT channel, target, morning_briefing, weekly_digest, breaking_topics, breaking_sources, is_active, updated_at "
        "FROM synced_delivery_subscriptions WHERE sync_token = %s",
        (token,),
    )
    return {
        "status": "success",
        "subscription": _normalize_server_delivery_row(row),
        "updated_at": row.get("updated_at") if row else None,
    }


@app.post("/api/profile/delivery")
async def save_profile_delivery(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing sync token")

    profile = db.execute_one(
        "SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Synced profile not found")

    subscription = _normalize_server_delivery_subscription(payload.get("subscription") or {})
    db.execute(
        """INSERT INTO synced_delivery_subscriptions
           (sync_token, channel, target, morning_briefing, weekly_digest, breaking_topics, breaking_sources, is_active, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
           ON CONFLICT (sync_token) DO UPDATE SET
             channel = EXCLUDED.channel,
             target = EXCLUDED.target,
             morning_briefing = EXCLUDED.morning_briefing,
             weekly_digest = EXCLUDED.weekly_digest,
             breaking_topics = EXCLUDED.breaking_topics,
             breaking_sources = EXCLUDED.breaking_sources,
             is_active = EXCLUDED.is_active,
             updated_at = NOW()""",
        (
            token,
            subscription["channel"],
            subscription["target"],
            subscription["morningBriefing"],
            subscription["weeklyDigest"],
            subscription["breakingTopics"],
            subscription["breakingSources"],
            subscription["isActive"],
        ),
        fetch=False,
    )
    return {
        "status": "success",
        "subscription": subscription,
    }


@app.post("/api/profile/suggestion-event")
async def save_suggestion_events(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    client_id = str(payload.get("clientId") or "").strip()[:64]
    raw_events = payload.get("events") or []

    if not client_id:
        raise HTTPException(status_code=400, detail="Missing client id")
    if not isinstance(raw_events, list) or not raw_events:
        raise HTTPException(status_code=400, detail="Missing suggestion events")

    clean_token = ""
    if token:
        profile = db.execute_one(
            "SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s",
            (token,),
        )
        if profile:
            clean_token = token

    accepted = 0
    for item in raw_events[:24]:
        if not isinstance(item, dict):
            continue
        surface = _normalize_suggestion_surface(item.get("surface"))
        event_type = _normalize_suggestion_event_type(item.get("eventType"))
        suggestion_kind = _normalize_suggestion_kind(item.get("suggestionKind"))
        value = str(item.get("value") or "").strip()[:160]
        if not surface or not event_type:
            continue
        if event_type in {"impression", "follow"} and not suggestion_kind:
            continue
        db.execute(
            """INSERT INTO suggestion_surface_events
               (sync_token, client_id, surface, suggestion_kind, event_type, value, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (
                clean_token or None,
                client_id,
                surface,
                suggestion_kind or None,
                event_type,
                value,
                json.dumps({}),
            ),
            fetch=False,
        )
        accepted += 1

    delete_cache("stats:full")
    return {
        "status": "success",
        "accepted": accepted,
    }


@app.get("/api/delivery/track/{event_type}")
async def track_delivery_event(event_type: str, event_id: int = Query(..., ge=1), redirect: str = Query("/briefing")):
    clean_type = str(event_type or "").strip().lower()
    if clean_type not in {"open", "click"}:
        raise HTTPException(status_code=400, detail="Invalid event type")

    parent = db.execute_one(
        "SELECT sync_token, delivery_kind, channel, target, cluster_id, metadata FROM delivery_tracking_events WHERE id = %s AND event_type = 'send'",
        (event_id,),
    )
    if parent:
        db.execute(
            """INSERT INTO delivery_tracking_events
               (sync_token, parent_event_id, event_type, delivery_kind, channel, target, cluster_id, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (
                parent.get("sync_token"),
                event_id,
                clean_type,
                parent.get("delivery_kind"),
                parent.get("channel") or "ntfy",
                parent.get("target") or "",
                parent.get("cluster_id"),
                json.dumps({"redirect": _safe_tracking_redirect_path(redirect)}),
            ),
            fetch=False,
        )

    return RedirectResponse(url=f"{_public_site_url}{_safe_tracking_redirect_path(redirect)}", status_code=302)

@app.get("/api/intelligence/source-pulse")
async def get_source_pulse():
    """Aggregates sentiment data and speed metrics by source."""
    # We query cluster_summaries joined with articles to get source-level metrics
    # Plus a subquery to count how many times they were the earliest article in a cluster
    sql = """
        WITH first_reporters AS (
            SELECT DISTINCT ON (cluster_id) source, cluster_id
            FROM articles
            ORDER BY cluster_id, created_at ASC
        )
        SELECT 
            a.source,
            AVG(CAST(s.sentiment->>'score' AS REAL)) as avg_sentiment,
            AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity,
            AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism,
            COUNT(DISTINCT a.cluster_id) as cluster_count,
            (SELECT COUNT(*) FROM first_reporters fr 
             WHERE fr.source = a.source 
               AND fr.cluster_id IN (SELECT cluster_id FROM articles WHERE created_at >= NOW() - INTERVAL '7 days')
            ) as first_report_count
        FROM cluster_summaries s
        JOIN articles a ON s.cluster_id = a.cluster_id
        WHERE s.sentiment IS NOT NULL
          AND s.created_at >= NOW() - INTERVAL '7 days'
        GROUP BY a.source
        HAVING COUNT(DISTINCT a.cluster_id) >= 3
        ORDER BY cluster_count DESC
    """
    rows = db.execute(sql)
    return {"status": "success", "data": rows}


@app.get("/api/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    """Returns detailed profile, media stats, and recent clusters for an entity."""
    entity = db.execute_one("""
        SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score
        FROM knowledge_entities WHERE name = %s
    """, (name,))
    
    if not entity:
        # Fallback: if not in knowledge base but exists in tags, create a transient profile
        exists = db.execute_one("SELECT 1 FROM cluster_metadata WHERE %s = ANY(tags) LIMIT 1", (name,))
        if not exists:
            raise HTTPException(status_code=404, detail="Entity not found")
        entity = {
            "name": name,
            "type": "ENTITY",
            "total_mentions": 0,
            "first_seen": None,
            "last_seen": None,
            "sentiment_score": 0
        }
    
    # 1. Get top relationships
    relationships = db.execute("""
        SELECT 
            CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
            weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC LIMIT 8
    """, (name, name, name))
    
    # 2. Get Top Media Outlets
    media_stats = db.execute("""
        SELECT a.source, COUNT(DISTINCT a.cluster_id) as mention_count
        FROM articles a
        JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
        WHERE %s = ANY(m.tags)
        GROUP BY a.source
        ORDER BY mention_count DESC LIMIT 5
    """, (name,))

    # 3. Get Recent Clusters
    recent_clusters = db.execute("""
        SELECT
            c.cluster_id,
            (SELECT title FROM articles WHERE cluster_id = c.cluster_id ORDER BY created_at DESC LIMIT 1) as title,
            c.updated_at as created_at,
            s.summary,
            s.sentiment
        FROM cluster_metadata c
        LEFT JOIN cluster_summaries s ON c.cluster_id = s.cluster_id
        WHERE %s = ANY(c.tags)
        ORDER BY c.updated_at DESC LIMIT 10
    """, (name,))
    
    # Process clusters to include bullets and clean sentiment
    processed_clusters = []
    for c in recent_clusters:
        bullets = []
        if c["summary"]:
            bullets = [
                re.sub(r'^[-•*]\s*', '', line).strip()
                for line in c["summary"].split('\n')
                if line.strip() and not line.strip().lower().startswith('статии:')
            ]
        
        sent_data = c["sentiment"]
        if isinstance(sent_data, str):
            try: sent_data = json.loads(sent_data)
            except: sent_data = None

        processed_clusters.append({
            "cluster_id": c["cluster_id"],
            "title": cleanAndDecode(c["title"]),
            "created_at": c["created_at"],
            "bullets": bullets[:2],
            "sentiment": sent_data
        })

    return {
        "profile": entity,
        "related": relationships,
        "media": media_stats,
        "clusters": processed_clusters
    }

@app.get("/api/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    """Returns the most mentioned entities."""
    cache_key = f"api:top-entities:{limit}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    fetch_limit = max(limit * 4, 24)
    rows = db.execute("""
        SELECT name, type, total_mentions 
        FROM knowledge_entities 
        ORDER BY total_mentions DESC LIMIT %s
    """, (fetch_limit,))

    filtered = []
    seen = set()
    for row in rows:
        normalized_name = normalize_tag_name(row["name"])
        if not _is_valid_focus_entity(normalized_name, row.get("type")):
            continue
        dedupe_key = normalized_name.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        filtered.append({
            "name": normalized_name,
            "type": row.get("type"),
            "total_mentions": row.get("total_mentions"),
        })
        if len(filtered) >= limit:
            break
            
    set_cache(cache_key, filtered, ttl=600)  # 10 minutes
    return filtered


@app.get("/api/intelligence/entity/{name}/topics")
async def get_entity_topics(name: str):
    """Returns the most frequent thematic topics associated with an entity."""
    sql = """
        SELECT a.topic, COUNT(*) as count
        FROM articles a
        JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id
        WHERE ce.entity_name = %s AND a.topic IS NOT NULL
        GROUP BY a.topic
        ORDER BY count DESC
        LIMIT 5
    """
    rows = db.execute(sql, (name,))
    return {"status": "success", "data": rows}


@app.get("/api/intelligence/live-map")
async def get_live_map():
    """Returns a list of sources and their recent activity for the live map."""
    try:
        sql = """
            SELECT source, COUNT(*) as activity_score
            FROM articles 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY source
            ORDER BY activity_score DESC
        """
        rows = db.execute(sql)
        return {"status": "success", "data": rows}
    except Exception as e:
        log.error(f"Live Map Error: {e}")
        return {"status": "error", "data": []}

@app.get("/api/intelligence/compare-sources")
async def compare_sources(s1: str, s2: str):
    """Side-by-side comparison of two media outlets."""
    try:
        sql = """
            SELECT 
                a.source,
                AVG(CAST(s.sentiment->>'score' AS REAL)) as avg_sentiment,
                AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity,
                AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism,
                COUNT(DISTINCT a.cluster_id) as cluster_count
            FROM cluster_summaries s
            JOIN articles a ON s.cluster_id = a.cluster_id
            WHERE a.source = ANY(%s)
              AND s.sentiment IS NOT NULL
              AND s.created_at >= NOW() - INTERVAL '30 days'
            GROUP BY a.source
        """
        rows = db.execute(sql, ([s1, s2],))
        return {"status": "success", "data": rows}
    except Exception as e:
        log.error(f"Source Comparison Error: {e}")
        return {"status": "error", "data": []}

@app.get("/api/news")
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    sort: str = "recent",
    page: int = 0,
    page_size: int = 24
):
    # Cache key based on all parameters
    cache_key = f"api:news:{q}:{category}:{topic}:{entity}:{sort}:{page}:{page_size}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        # Clamp pagination + query length to prevent abuse
        page = max(0, min(int(page or 0), API_MAX_PAGE))
        page_size = max(1, min(int(page_size or 24), 50))
        row_limit = _news_row_limit(page, page_size)
        if q:
            q = q.strip()[:API_MAX_Q_LEN]

        # Hybrid Search if query is present
        if q:
            from embeddings import generate_query_embedding
            query_vec = generate_query_embedding(q)
            if query_vec:
                rows = db.hybrid_search(q, query_vec, limit=row_limit)
            else:
                # Fallback to simple FTS if embedding fails
                rows = db.search_articles(q, limit=row_limit)
        elif entity:
            sql = """
                SELECT a.* FROM articles a
                JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id
                WHERE ce.entity_name = %s
                ORDER BY a.created_at DESC LIMIT %s
            """
            params = [entity, row_limit]
            rows = db.execute(sql, tuple(params))
        elif topic:
            sql = "SELECT * FROM articles WHERE topic = %s ORDER BY created_at DESC LIMIT %s"
            params = [topic, row_limit]
            rows = db.execute(sql, tuple(params))
        elif category:
            sql = "SELECT * FROM articles WHERE category = %s ORDER BY created_at DESC LIMIT %s"
            params = [category, row_limit]
            rows = db.execute(sql, tuple(params))
        else:
            sql = "SELECT * FROM articles ORDER BY created_at DESC LIMIT %s"
            rows = db.execute(sql, (row_limit,))

        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            clusters[r['cluster_id']].append(r)

        ranked_clusters = [annotate_cluster_articles(arts) for arts in clusters.values()]
        
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster_for_homepage, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]

        # Fetch metadata and synthesis status
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        if cid_list:
            metadata_rows = db.execute(
                "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                (cid_list,)
            )
            rep_images = {r['cluster_id']: r['representative_image'] for r in metadata_rows}
            
            synthesis_ids = set(db.get_synthesis_ids(cid_list))
        else:
            rep_images = {}
            synthesis_ids = set()

        result = []
        for arts in paged_clusters:
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            homepage_score = score_cluster_for_homepage(arts)
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": main.get('reading_time', 1),
                "score": round(s, 3),
                "homepage_score": round(homepage_score, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_fact_check": any(a.get("is_fact_check") for a in arts),
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", [])
            })

        final_response = {
            "status": "success",
            "clusters": result,
            "page": page,
            "has_more": len(ranked_clusters) > start + page_size
        }
        set_cache(cache_key, final_response, ttl=180)  # 3 minutes
        return final_response
    except Exception as e:
        log.error(f"FastAPI News Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

@app.get("/api/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    """Returns detailed information for a specific cluster."""
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
        
    try:
        # 1. Fetch articles
        rows = db.execute(
            "SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", 
            (cluster_id,)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cluster not found")
            
        articles = annotate_cluster_articles(rows)
        for a in articles:
            a['reading_time'] = calculate_reading_time(a.get('description', ''))

        # 2. Fetch synthesis and perspectives
        s_row = db.execute_one(
            "SELECT summary, generated_article, perspectives, created_at, sentiment, verification_report FROM cluster_summaries WHERE cluster_id = %s",
            (cluster_id,)
        )
        synthesis = s_row["summary"] if s_row else None
        generated_article = s_row["generated_article"] if s_row else None
        sentiment = s_row["sentiment"] if s_row and s_row["sentiment"] else None
        if isinstance(sentiment, str):
            try:
                sentiment = json.loads(sentiment)
            except json.JSONDecodeError:
                log.warning(f"Malformed JSON in sentiment for cluster {cluster_id}")
                sentiment = None

        verification_report = s_row["verification_report"] if s_row and s_row["verification_report"] else None
        if isinstance(verification_report, str):
            try:
                verification_report = json.loads(verification_report)
            except json.JSONDecodeError:
                log.warning(f"Malformed JSON in verification_report for cluster {cluster_id}")
                verification_report = None
        # Parse synthesis into bullets for the 'ai_summary_bullets' field
        ai_summary_bullets = []
        if synthesis:
            ai_summary_bullets = [
                re.sub(r'^[-•*]\s*', '', line).strip()
                for line in synthesis.split('\n')
                if line.strip() and not line.strip().lower().startswith('статии:')
            ]
            
        perspectives = s_row["perspectives"] if s_row and s_row["perspectives"] else []
        if isinstance(perspectives, str):
            try:
                perspectives = json.loads(perspectives)
            except json.JSONDecodeError:
                log.warning(f"Malformed JSON in perspectives for cluster {cluster_id}")
                perspectives = []
        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))

        # 3. Fetch metadata (tags, etc)
        m_row = db.execute_one(
            "SELECT tags, topics FROM cluster_metadata WHERE cluster_id = %s", 
            (cluster_id,)
        )
        tags = filter_cluster_tags(m_row["tags"] if m_row else [])
        topics = m_row["topics"] if m_row else []

        # 4. Related clusters (Semantic)
        related = []
        lead_article = articles[0]
        if lead_article.get("embedding"):
            # Ensure embedding is a list
            if isinstance(lead_article["embedding"], str):
                lead_vec = json.loads(lead_article["embedding"])
            else:
                lead_vec = list(lead_article["embedding"])
            
            # Find semantically similar clusters
            related_results = db.search_semantic(lead_vec, limit=8)
            
            seen_cids = {cluster_id}
            related_cids = []
            for r in related_results:
                cid = r.get("cluster_id")
                if cid and cid not in seen_cids:
                    related_cids.append(cid)
                    seen_cids.add(cid)
                    if len(related_cids) >= 4:
                        break
            
            if related_cids:
                r_rows = db.execute("""
                    SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags 
                    FROM articles a 
                    LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
                    WHERE a.cluster_id = ANY(%s)
                """, (related_cids,))
                
                # Group and annotate
                r_grouped = defaultdict(list)
                for r in r_rows:
                    r_grouped[r["cluster_id"]].append(r)
                
                for cid in related_cids:
                    arts = r_grouped.get(cid)
                    if not arts: continue
                    ranked = annotate_cluster_articles(arts)
                    main = ranked[0]
                    related.append({
                        "cluster_id": cid,
                        "title": main["title"],
                        "image_url": main.get("image_url"),
                        "tags": filter_cluster_tags(main.get("cluster_tags", [])),
                        "relationship_label": "Сродна тема"
                    })

        # 5. Build timeline
        chrono_articles = sorted(articles, key=lambda x: x['created_at'])
        first_reporter = {
            "source": chrono_articles[0]['source'],
            "created_at": chrono_articles[0]['created_at']
        } if chrono_articles else None

        timeline = []
        for i, a in enumerate(chrono_articles):
            is_major = (a.get('source_signal') or {}).get('trust_level', 0) >= 0.8
            milestone = None
            if i == 0: milestone = "ПОЧЕТОК"
            elif i == len(chrono_articles) // 2 and len(chrono_articles) >= 4: milestone = "ДИВЕРГЕНЦИЈА"
            elif i == len(chrono_articles) - 1 and len(chrono_articles) >= 3: milestone = "КОНСЕНЗУС"
            else: milestone = "РАЗВОЈ"

            timeline.append({
                "article_id": a['id'],
                "title": cleanAndDecode(a['title']),
                "source": a['source'],
                "created_at": a['created_at'],
                "is_first": i == 0,
                "is_major": is_major or milestone in ("ПОЧЕТОК", "ДИВЕРГЕНЦИЈА", "КОНСЕНЗУС"),
                "milestone": milestone
            })

        return {
            "status": "success",
            "data": {
                "cluster_id": cluster_id,
                "articles": articles,
                "timeline": timeline,
                "first_reporter": first_reporter,
                "synthesis": synthesis,
                "generated_article": generated_article,
                "sentiment": sentiment,
                "verification_report": verification_report,
                "has_fact_check": any(a.get("is_fact_check") for a in articles),
                "ai_summary_bullets": ai_summary_bullets,
                "synthesis_updated_at": freshness["synthesis_updated_at"],
                "synthesis_freshness": {
                    "is_stale": freshness["is_stale"],
                    "new_article_count": freshness["new_article_count"],
                    "reasons": freshness["reasons"],
                },
                "perspectives": perspectives,
                "tags": tags,
                "topics": topics,
                "related": related,
                "total_reading_time": sum(a['reading_time'] for a in articles)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"FastAPI Cluster Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch cluster detail")


@app.post("/api/cluster/{cluster_id}/ask")
async def ask_cluster(cluster_id: str, request: Request):
    """Answers a question using only the current cluster's context."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    question = str((payload or {}).get("question") or "").strip()
    try:
        return await _build_cluster_answer_payload(cluster_id, question)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[fastapi/ask_cluster] unexpected error for {cluster_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to answer cluster question")


@app.post("/api/intelligence/recommendations")
async def get_personalized_recommendations(request: Request):
    """
    Returns clusters similar to the user's reading history and followed topics.
    Payload: { recentlyRead: string[], followedTopics: string[], limit: int }
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    recent_ids = payload.get("recentlyRead", [])[:10]
    followed_topics = payload.get("followedTopics", [])
    limit = min(int(payload.get("limit", 6)), 20)

    if not recent_ids and not followed_topics:
        return {"status": "success", "clusters": []}

    # 1. Get embeddings for recently read lead articles
    user_vectors = []
    if recent_ids:
        rows = db.execute(
            "SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL LIMIT 20",
            (recent_ids,)
        )
        for r in rows:
            if r["embedding"]:
                if isinstance(r["embedding"], str):
                    vec = json.loads(r["embedding"])
                else:
                    vec = list(r["embedding"])
                user_vectors.append(vec)

    # 2. Add vectors for followed topics
    from embeddings import generate_query_embedding
    for topic in followed_topics:
        vec = generate_query_embedding(topic)
        if vec:
            user_vectors.append(vec)

    if not user_vectors:
        return {"status": "success", "clusters": []}

    # 3. Calculate mean vector
    import numpy as np
    avg_vec = np.mean(user_vectors, axis=0).tolist()

    # 4. Search semantic
    results = db.search_semantic(avg_vec, limit=limit * 3)
    
    # 5. Group by cluster and format
    seen_clusters = set(recent_ids)
    cluster_ids = []
    for r in results:
        cid = r.get("cluster_id")
        if cid and cid not in seen_clusters:
            cluster_ids.append(cid)
            seen_clusters.add(cid)
            if len(cluster_ids) >= limit:
                break

    if not cluster_ids:
        return {"status": "success", "clusters": []}

    rows = db.execute(
        "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
        (cluster_ids,)
    )
    
    clusters_map = {}
    for row in rows:
        cid = row["cluster_id"]
        clusters_map.setdefault(cid, []).append(row)

    from utils import score_cluster
    formatted = []
    for cid in cluster_ids:
        articles = clusters_map.get(cid, [])
        if not articles: continue
        
        s_row = db.execute_one("SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s", (cid,))
        m_row = db.execute_one("SELECT tags, representative_image FROM cluster_metadata WHERE cluster_id = %s", (cid,))
        
        formatted.append({
            "cluster_id": cid,
            "articles": articles,
            "representative_image": m_row["representative_image"] if m_row else None,
            "score": score_cluster(articles),
            "has_synthesis": bool(s_row and s_row["summary"]),
            "is_breaking": any(a.get("is_breaking") for a in articles),
            "reason": "Предлог за Вас"
        })

    return {"status": "success", "clusters": formatted}


@app.post("/api/chat_cluster")
async def chat_cluster(request: Request):
    try:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        cluster_id = str((payload or {}).get("cluster_id") or "").strip()
        query = str((payload or {}).get("query") or "").strip()
        if not cluster_id or not query:
            raise HTTPException(status_code=400, detail="cluster_id and query are required")

        answer_payload = await _build_cluster_answer_payload(cluster_id, query)
        answer_payload["response"] = answer_payload["answer"]
        return answer_payload
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[fastapi/chat_cluster] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process query")


@app.get("/api/live")
async def get_live():
    return StreamingResponse(event_stream("updates"), media_type="text/event-stream")


@app.get("/api/weather")
async def get_weather():
    cached = cached_response("weather:skopje", ttl=900)
    if cached:
        return cached
    try:
        weather_req = urllib.request.Request(
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=41.9981&longitude=21.4254"
            "&current=temperature_2m,weather_code&timezone=Europe%2FSkopje",
            headers={"User-Agent": "Presek/6.0"},
        )
        aqi_req = urllib.request.Request(
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            "?latitude=41.9981&longitude=21.4254"
            "&current=us_aqi&timezone=Europe%2FSkopje",
            headers={"User-Agent": "Presek/6.0"},
        )
        with urllib.request.urlopen(weather_req, timeout=5) as response:
            weather = json.loads(response.read())
        with urllib.request.urlopen(aqi_req, timeout=5) as response:
            aqi = json.loads(response.read())

        temp = round(weather["current"]["temperature_2m"])
        code = weather["current"]["weather_code"]
        icon = _WMO_ICON.get(code, "🌡️")
        result = {"temp": temp, "icon": icon, "aqi": aqi["current"]["us_aqi"]}
        set_cache("weather:skopje", result, ttl=900)
        return result
    except Exception as e:
        log.warning(f"[fastapi/weather] {e}")
        return {"temp": None, "icon": "🌡️", "aqi": None}

@app.get("/api/briefing")
async def get_briefing():
    try:
        row = db.execute_one(
            "SELECT date, content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row:
            row = db.execute_one(
                "SELECT date, content FROM daily_briefings ORDER BY date DESC LIMIT 1"
            )
        if not row:
            fallback_rows = db.execute(
                "SELECT cluster_id, title, description, source, category, topic, created_at "
                "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 10"
            )
            return {
                "date": datetime.date.today().isoformat(),
                "content": generate_daily_brief_fallback(fallback_rows),
                "generated_locally": True,
            }

        return {
            "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
            "content": row["content"] or ""
        }
    except Exception as e:
        log.error(f"FastAPI Briefing Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing")

@app.get("/api/archive")
async def get_archive(
    date: str = Query(...),
    source: str = "",
    topic: str = "",
    page: int = 0,
    page_size: int = 50
):
    """Return clustered archive data for a specific date."""
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')

        offset = page * page_size
        where_clauses = ["created_at::date = %s"]
        params = [date]

        if source:
            where_clauses.append("source = %s")
            params.append(source)

        if topic:
            where_clauses.append("topic = %s")
            params.append(topic)

        where_sql = " AND ".join(where_clauses)

        rows = db.execute(
            "SELECT * FROM articles "
            f"WHERE {where_sql} "
            "ORDER BY created_at DESC LIMIT 1500",
            tuple(params)
        )

        clusters = defaultdict(list)
        for row in rows:
            row["reading_time"] = calculate_reading_time(row.get("description", ""))
            clusters[row["cluster_id"]].append(row)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        ranked_clusters.sort(key=score_cluster, reverse=True)

        paged_clusters = ranked_clusters[offset: offset + page_size]
        cluster_ids = [cluster[0]["cluster_id"] for cluster in paged_clusters]
        synthesis_ids = set(db.get_synthesis_ids(cluster_ids)) if cluster_ids else set()
        metadata_rows = db.execute(
            "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
            (cluster_ids or [""],)
        ) if cluster_ids else []
        rep_images = {r["cluster_id"]: r["representative_image"] for r in metadata_rows}

        cluster_payload = []
        for arts in paged_clusters:
            cid = arts[0]["cluster_id"]
            s = score_cluster(arts)
            cluster_payload.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": arts[0].get("reading_time", 1),
                "score": round(s, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
            })

        total = db.execute_one(
            f"SELECT COUNT(*) FROM articles WHERE {where_sql}",
            tuple(params)
        )["count"]
        sources = db.execute_one(
            f"SELECT COUNT(DISTINCT source) FROM articles WHERE {where_sql}",
            tuple(params)
        )["count"]
        top_sources = db.execute(
            f"SELECT source, COUNT(*) AS n FROM articles WHERE {where_sql} "
            "GROUP BY source ORDER BY n DESC LIMIT 8",
            tuple(params)
        )
        top_topics = db.execute(
            f"SELECT topic, COUNT(*) AS n FROM articles WHERE {where_sql} "
            "GROUP BY topic ORDER BY n DESC LIMIT 8",
            tuple(params)
        )

        return {
            "clusters": cluster_payload,
            "total": total,
            "sources": sources,
            "date": date,
            "source": source,
            "topic": topic,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < len(ranked_clusters),
            "total_clusters": len(ranked_clusters),
            "top_sources": [dict(r) for r in top_sources],
            "top_topics": [dict(r) for r in top_topics],
        }
    except Exception as e:
        log.error(f"FastAPI Archive Error: {e}")
        return {"status": "error", "message": "Failed to load archive"}

@app.get("/api/stats")
async def get_stats():
    try:
        return {"status": "success", "data": db.get_stats()}
    except Exception as e:
        log.error(f"FastAPI Stats Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/api/stats/summary")
async def get_stats_summary():
    """Public stats for the homepage including quote of the day."""
    cache_key = "api:stats:summary"
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        last_24h = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )["count"] or 0
        total_feeds = db.execute_one(
            "SELECT COUNT(*) FROM sources WHERE is_active = TRUE"
        )["count"] or 0
        
        quote_row = db.execute_one("""
            SELECT s.quote, s.cluster_id, 
                   (SELECT title FROM articles WHERE cluster_id = s.cluster_id ORDER BY created_at DESC LIMIT 1) as title
            FROM cluster_summaries s
            WHERE s.quote IS NOT NULL AND s.quote != ''
              AND s.created_at >= NOW() - INTERVAL '48 hours'
            ORDER BY RANDOM() LIMIT 1
        """)
        
        result = {
            "last_24h": last_24h,
            "total_feeds": total_feeds,
            "quote_of_the_day": quote_row
        }
        set_cache(cache_key, result, ttl=300)  # 5 minutes
        return result
    except Exception as e:
        log.error(f"Stats Summary Error: {e}")
        return {"last_24h": 0, "total_feeds": 0, "quote_of_the_day": None}

@app.post("/api/newsletter/subscribe")
async def subscribe_newsletter(request: Request):
    """Subscribes an email to the daily briefing."""
    try:
        body = await request.json()
        email = str(body.get("email", "")).strip().lower()
        if not email or "@" not in email:
            return {"status": "error", "message": "Невалидна е-пошта."}
        
        db.execute(
            "INSERT INTO newsletter_subscribers (email) VALUES (%s) ON CONFLICT (email) DO UPDATE SET is_active = TRUE",
            (email,), fetch=False
        )
        return {"status": "success", "message": "Успешно се пријавивте за дневниот брифинг!"}
    except Exception as e:
        log.error(f"Newsletter Subscribe Error: {e}")
        return {"status": "error", "message": "Грешка при пријавување."}

@app.get("/api/stats/full")
async def get_stats_full(request: Request):
    if not _source_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        cached = cached_response("stats:full", ttl=120)
        if cached:
            return cached

        total = db.execute_one("SELECT COUNT(*) FROM articles")["count"] or 0
        last_24h = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )["count"] or 0
        summarized = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''"
        )["count"] or 0
        summarized_24h = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND summary IS NOT NULL AND summary != ''"
        )["count"] or 0
        summarized_pct = round((summarized_24h / last_24h * 100), 1) if last_24h else 0

        db_size_row = db.execute_one(
            "SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 1) AS mb"
        )
        db_size_mb = float(db_size_row["mb"]) if db_size_row else 0

        total_feeds = db.execute_one(
            "SELECT COUNT(DISTINCT source) AS n FROM articles"
        )["n"] or 0

        dates_row = db.execute_one(
            "SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest FROM articles"
        )
        oldest_article = dates_row["oldest"].isoformat() if dates_row and dates_row["oldest"] else None
        newest_article = dates_row["newest"].isoformat() if dates_row and dates_row["newest"] else None

        by_source = db.execute(
            "SELECT source, COUNT(*) AS n FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )

        by_category = [
            {"cat": r["category"] or "Друго", "n": r["n"]}
            for r in db.execute(
                "SELECT category, COUNT(*) AS n FROM articles GROUP BY category ORDER BY n DESC LIMIT 8"
            )
        ]

        velocity = db.execute(
            "SELECT date_trunc('hour', created_at) AS t, COUNT(*) AS n "
            "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY t ORDER BY t"
        )
        velocity_out = [{"t": r["t"].isoformat(), "n": r["n"]} for r in velocity]

        speed_leaderboard = db.execute(
            "SELECT source, COUNT(*) AS first_count FROM ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source "
            "  FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' "
            "  ORDER BY cluster_id, created_at ASC"
            ") first_articles GROUP BY source ORDER BY first_count DESC LIMIT 8"
        )

        profile_stats_row = db.execute_one(
            "SELECT "
            "COUNT(*) AS synced_profiles, "
            "COUNT(*) FILTER (WHERE updated_at >= NOW() - INTERVAL '7 days') AS active_profiles_7d, "
            "COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'recentClusters', '[]'::jsonb)) > 0) AS profiles_with_recent_reads, "
            "COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) > 0) AS profiles_following_topics, "
            "COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedSources', '[]'::jsonb)) > 0) AS profiles_following_sources "
            "FROM synced_reader_profiles"
        ) or {}
        delivery_stats_row = db.execute_one(
            "SELECT "
            "COUNT(*) FILTER (WHERE is_active = TRUE) AS delivery_active, "
            "COUNT(*) FILTER (WHERE COALESCE(target, '') != '') AS delivery_targets, "
            "COUNT(*) FILTER (WHERE morning_briefing = TRUE) AS morning_briefings, "
            "COUNT(*) FILTER (WHERE weekly_digest = TRUE) AS weekly_digests, "
            "COUNT(*) FILTER (WHERE breaking_topics = TRUE) AS breaking_topic_alerts, "
            "COUNT(*) FILTER (WHERE breaking_sources = TRUE) AS breaking_source_alerts "
            "FROM synced_delivery_subscriptions"
        ) or {}
        top_followed_topics = db.execute(
            "SELECT value AS topic, COUNT(*) AS followers "
            "FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) AS value "
            "GROUP BY value ORDER BY followers DESC, topic ASC LIMIT 6"
        )
        top_followed_sources = db.execute(
            "SELECT value AS source, COUNT(*) AS followers "
            "FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedSources', '[]'::jsonb)) AS value "
            "GROUP BY value ORDER BY followers DESC, source ASC LIMIT 6"
        )
        tracking_stats_row = db.execute_one(
            "SELECT "
            "COUNT(*) FILTER (WHERE event_type = 'send') AS sends_7d, "
            "COUNT(*) FILTER (WHERE event_type = 'open') AS opens_7d, "
            "COUNT(*) FILTER (WHERE event_type = 'click') AS clicks_7d "
            "FROM delivery_tracking_events "
            "WHERE created_at >= NOW() - INTERVAL '7 days'"
        ) or {}
        tracking_performance_rows = db.execute(
            "SELECT delivery_kind, "
            "COUNT(*) FILTER (WHERE event_type = 'send') AS sends, "
            "COUNT(*) FILTER (WHERE event_type = 'open') AS opens, "
            "COUNT(*) FILTER (WHERE event_type = 'click') AS clicks "
            "FROM delivery_tracking_events "
            "WHERE created_at >= NOW() - INTERVAL '30 days' "
            "GROUP BY delivery_kind"
        )
        suggestion_surface_rows = db.execute(
            "SELECT surface, "
            "COUNT(*) FILTER (WHERE event_type = 'impression') AS impressions, "
            "COUNT(*) FILTER (WHERE event_type = 'follow') AS follows, "
            "COUNT(*) FILTER (WHERE event_type = 'dismiss') AS dismissals, "
            "COUNT(*) FILTER (WHERE event_type = 'follow' AND suggestion_kind = 'topic') AS topic_follows, "
            "COUNT(*) FILTER (WHERE event_type = 'follow' AND suggestion_kind = 'source') AS source_follows "
            "FROM suggestion_surface_events "
            "WHERE created_at >= NOW() - INTERVAL '30 days' "
            "GROUP BY surface"
        )
        suggestion_kind_rows = db.execute(
            "SELECT suggestion_kind, "
            "COUNT(*) FILTER (WHERE event_type = 'impression') AS impressions, "
            "COUNT(*) FILTER (WHERE event_type = 'follow') AS follows, "
            "COUNT(*) FILTER (WHERE event_type = 'dismiss') AS dismissals "
            "FROM suggestion_surface_events "
            "WHERE created_at >= NOW() - INTERVAL '30 days' "
            "AND COALESCE(suggestion_kind, '') != '' "
            "GROUP BY suggestion_kind"
        )
        suggestion_surface_period_rows = db.execute(
            "SELECT surface, "
            "COUNT(*) FILTER (WHERE event_type = 'impression' AND created_at >= NOW() - INTERVAL '7 days') AS current_impressions, "
            "COUNT(*) FILTER (WHERE event_type = 'follow' AND created_at >= NOW() - INTERVAL '7 days') AS current_follows, "
            "COUNT(*) FILTER (WHERE event_type = 'impression' AND created_at < NOW() - INTERVAL '7 days' AND created_at >= NOW() - INTERVAL '14 days') AS previous_impressions, "
            "COUNT(*) FILTER (WHERE event_type = 'follow' AND created_at < NOW() - INTERVAL '7 days' AND created_at >= NOW() - INTERVAL '14 days') AS previous_follows "
            "FROM suggestion_surface_events "
            "WHERE created_at >= NOW() - INTERVAL '14 days' "
            "GROUP BY surface"
        )

        result = {
            "total_articles": total,
            "last_24h": last_24h,
            "summarized_pct": summarized_pct,
            "summarized_24h": summarized_24h,
            "summarized_all_time": summarized,
            "uptime": "Online",
            "db_size_mb": db_size_mb,
            "total_feeds": total_feeds,
            "oldest_article": oldest_article,
            "new_article": newest_article,
            "by_source": [{"source": r["source"], "n": r["n"]} for r in by_source],
            "by_category": by_category,
            "velocity": velocity_out,
            "speed_leaderboard": [{"source": r["source"], "first_count": r["first_count"]} for r in speed_leaderboard],
            "sentiment_index": [],
            "editor_analytics": build_editor_analytics_payload(
                profile_stats_row,
                delivery_stats_row,
                top_followed_topics,
                top_followed_sources,
                tracking_stats_row,
                tracking_performance_rows,
                suggestion_surface_rows,
                suggestion_kind_rows,
                suggestion_surface_period_rows,
            ),
        }

        set_cache("stats:full", result, ttl=120)
        return result

    except Exception as e:
        log.error(f"FastAPI Stats Full Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/api/sources")
async def get_sources():
    """Return source reputation rows."""
    try:
        rows = db.execute(
            "SELECT name, country, category, credibility, is_active, last_fetched, pause_mode, pause_reason, paused_at "
            "FROM sources ORDER BY is_active DESC, name ASC"
        )
        pulse_rows = db.execute(
            "SELECT source, COUNT(*) as count FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY source"
        )
        speed_rows = db.execute(
            "SELECT source, COUNT(*) AS first_count FROM ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source "
            "  FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' "
            "  ORDER BY cluster_id, created_at ASC"
            ") first_articles GROUP BY source ORDER BY first_count DESC"
        )
        history_rows = db.execute(
            "WITH cluster_first AS ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source, created_at "
            "  FROM articles "
            "  WHERE created_at >= NOW() - INTERVAL '30 days' "
            "  ORDER BY cluster_id, created_at ASC"
            "), cluster_counts AS ("
            "  SELECT cluster_id, COUNT(DISTINCT source) AS source_count "
            "  FROM articles "
            "  WHERE created_at >= NOW() - INTERVAL '30 days' "
            "  GROUP BY cluster_id"
            "), source_weeks AS ("
            "  SELECT source, "
            "    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS recent_7d_volume, "
            "    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '14 days' AND created_at < NOW() - INTERVAL '7 days') AS previous_7d_volume "
            "  FROM articles "
            "  WHERE created_at >= NOW() - INTERVAL '14 days' "
            "  GROUP BY source"
            ") "
            "SELECT cf.source, "
            "  COUNT(*) AS lead_count_30d, "
            "  COUNT(*) FILTER (WHERE cc.source_count >= 2) AS corroborated_lead_count_30d, "
            "  COUNT(*) FILTER (WHERE cc.source_count = 1) AS solo_lead_count_30d, "
            "  COALESCE(sw.recent_7d_volume, 0) AS recent_7d_volume, "
            "  COALESCE(sw.previous_7d_volume, 0) AS previous_7d_volume "
            "FROM cluster_first cf "
            "LEFT JOIN cluster_counts cc ON cc.cluster_id = cf.cluster_id "
            "LEFT JOIN source_weeks sw ON sw.source = cf.source "
            "GROUP BY cf.source, sw.recent_7d_volume, sw.previous_7d_volume"
        )
        return build_source_reputation_rows(rows, pulse_rows, speed_rows, history_rows)
    except Exception as e:
        log.warning(f"FastAPI Sources Error: {e}")
        return []


@app.post("/api/sources/{name}/control")
async def control_source(name: str, request: Request):
    if not _source_admin_authorized(request):
        return _error_json("Unauthorized", 403)

    try:
        payload = await request.json()
    except Exception:
        return _error_json("Content-Type must be application/json", 415)

    source_name = str(name or "").strip()
    if not source_name:
        return _error_json("Source name is required", 400)

    action = str((payload or {}).get("action") or "").strip().lower()
    valid_actions = {"pause", "resume", "downrank", "uprank", "reset"}
    if action not in valid_actions:
        return _error_json("Invalid action", 400)

    source = db.execute_one(
        "SELECT name, country, category, credibility, is_active, last_fetched, pause_mode, pause_reason, paused_at FROM sources WHERE name = %s",
        (source_name,),
    )
    if not source:
        return _error_json("Source not found", 404)

    current_cred = float(source.get("credibility") or DEFAULT_CREDIBILITY)
    if action == "pause":
        db.execute(
            "UPDATE sources SET is_active = FALSE, pause_mode = 'manual', pause_reason = %s, paused_at = NOW() WHERE name = %s",
            ("Manual pause", source_name),
            fetch=False,
        )
    elif action == "resume":
        db.execute(
            "UPDATE sources SET is_active = TRUE, pause_mode = NULL, pause_reason = NULL, paused_at = NULL WHERE name = %s",
            (source_name,),
            fetch=False,
        )
        reset_source_policy(source_name)
    elif action == "downrank":
        db.execute(
            "UPDATE sources SET credibility = %s WHERE name = %s",
            (max(0.4, round(current_cred - 0.2, 2)), source_name),
            fetch=False,
        )
    elif action == "uprank":
        db.execute(
            "UPDATE sources SET credibility = %s WHERE name = %s",
            (min(3.0, round(current_cred + 0.2, 2)), source_name),
            fetch=False,
        )
    elif action == "reset":
        db.execute(
            "UPDATE sources SET credibility = %s, pause_mode = NULL, pause_reason = NULL, paused_at = NULL WHERE name = %s",
            (SOURCE_CREDIBILITY.get(source_name, DEFAULT_CREDIBILITY), source_name),
            fetch=False,
        )
        reset_source_policy(source_name)

    updated = db.execute_one(
        "SELECT name, country, category, credibility, is_active, last_fetched, pause_mode, pause_reason, paused_at FROM sources WHERE name = %s",
        (source_name,),
    )
    if updated:
        updated = dict(updated)
        updated["source_status"] = get_source_statuses().get(source_name)
    return {"status": "success", "source": updated}


@app.get("/api/sources/pulse")
async def get_sources_pulse():
    """Return top MK sources by article count in last 24h."""
    try:
        rows = db.execute(
            "SELECT source, COUNT(*) as n FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )
        return [{"source": r["source"], "count": r["n"]} for r in rows]
    except Exception as e:
        log.warning(f"FastAPI Pulse Error: {e}")
        return []


@app.get("/proxy")
async def proxy_image(url: str = Query(""), w: Optional[str] = Query(None)):
    if not url:
        return _error_json("Missing url parameter", 400)

    if url.startswith("/static/"):
        # Resolve under _STATIC_ROOT and verify the result stays inside it,
        # so encoded traversal sequences can't escape the static directory.
        relative = url[len("/static/"):].lstrip("/")
        try:
            candidate = (_STATIC_ROOT / relative).resolve()
            candidate.relative_to(_STATIC_ROOT.resolve())
        except (ValueError, RuntimeError):
            return _error_json("Blocked URL", 403)
        if not candidate.exists() or not candidate.is_file():
            return _error_json("Local file not found", 404)
        suffix = candidate.suffix.lower()
        content_type = {
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(suffix, "image/jpeg")
        return FileResponse(candidate, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})

    if not re.match(r'^https?://', url):
        return _error_json("Invalid URL scheme", 400)

    import time
    start_time = time.perf_counter()
    try:
        target_width = int(w) if w and str(w).isdigit() else 600
        target_width = max(20, min(1200, target_width))
    except ValueError:
        target_width = 600

    cache_key = f"proxy:webp:v2:{target_width}:{url}"
    cached = cached_response(cache_key, ttl=86400)
    if cached:
        return Response(
            bytes.fromhex(cached["data"]),
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    fetch_start = time.perf_counter()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        session = requests.Session()
        current_url = url
        response = None

        for _ in range(4):
            safe_ips = _resolve_public_ips(current_url)
            response = session.get(
                current_url,
                headers=headers,
                timeout=10,
                stream=True,
                verify=True,
                allow_redirects=False,
            )
            peer_ip = _peer_ip(response)
            if not peer_ip or peer_ip not in safe_ips:
                response.close()
                log.warning(f"[proxy/security] Blocked unsafe peer IP {peer_ip} for {url}")
                return _error_json("Blocked upstream target", 403)
            if 300 <= response.status_code < 400:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    return _error_json("Invalid upstream redirect", 502)
                current_url = urllib.parse.urljoin(current_url, location)
                if not re.match(r'^https?://', current_url):
                    return _error_json("Invalid upstream redirect", 502)
                continue
            break
        else:
            return _error_json("Too many upstream redirects", 502)

        if response.status_code != 200:
            log.warning(f"[proxy/fetch] Upstream {url} returned {response.status_code}")
            return _error_json("Failed to fetch image", response.status_code)

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in _PROXY_ALLOWED_TYPES:
            log.warning(f"[proxy/type] Unsupported content type {content_type} for {url}")
            return _error_json("Unsupported content type", 415)

        image_chunks = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > _PROXY_MAX_BYTES:
                response.close()
                log.warning(f"[proxy/size] Image too large ({total_bytes} bytes) for {url}")
                return _error_json("Image too large", 413)
            image_chunks.append(chunk)
        image_data = b"".join(image_chunks)
        fetch_duration = time.perf_counter() - fetch_start

        optimize_start = time.perf_counter()
        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(image_data))
        orig_w, orig_h = img.size
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > target_width:
            ratio = target_width / float(img.width)
            img = img.resize((target_width, int(float(img.height) * ratio)), Image.Resampling.LANCZOS)

        webp_io = BytesIO()
        quality = 20 if target_width <= 50 else 80
        img.save(webp_io, "WEBP", quality=quality, method=6)
        optimized_data = webp_io.getvalue()
        optimize_duration = time.perf_counter() - optimize_start

        set_cache(cache_key, {"data": optimized_data.hex(), "content_type": "image/webp"}, ttl=86400)
        
        total_duration = time.perf_counter() - start_time
        log.info(
            f"[proxy/perf] {url} -> {len(optimized_data)} bytes. "
            f"Total: {total_duration:.3f}s, Fetch: {fetch_duration:.3f}s, Optimize: {optimize_duration:.3f}s. "
            f"Original: {orig_w}x{orig_h}, Target: {target_width}w"
        )
        return Response(optimized_data, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})
    except socket.gaierror:
        return _error_json("Could not resolve hostname", 404)
    except PermissionError as e:
        return _error_json(str(e), 403)
    except ValueError as e:
        return _error_json(str(e), 403)
    except Exception as e:
        log.warning(f"[fastapi/proxy] Optimization error for {url}: {e}")
        return _error_json("Failed to process image", 502)

@app.get("/api/chat/stream")
async def chat_stream(
    cluster_id: str = Query(..., min_length=6, max_length=64),
    query: str = Query(..., min_length=1, max_length=500),
):
    """Streams AI response for a specific cluster."""
    
    # 1. Get cluster context
    articles = db.execute("SELECT title, description, source FROM articles WHERE cluster_id = %s LIMIT 10", (cluster_id,))
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    context = "\n".join([f"- [{a['source']}]: {a['title']}" for a in articles])

    async def generate():
        try:
            full_prompt = f"Context:\n{context}\n\nUser Question: {query}"
            result = await _call_ai_async(full_prompt, SYNTHESIS_SYSTEM_PROMPT, task_type="chat", stream=True)
            generator = result[0] if result else None
            provider = result[1] if result else None
            if generator:
                record_runtime_event("chat_path", mode=provider or "unknown", surface="chat_stream")
                async for chunk in generator:
                    if chunk:
                        yield f"data: {json.dumps({'token': chunk})}\n\n"
            else:
                record_runtime_event("chat_path", mode="local_fallback", surface="chat_stream")
            yield "data: [DONE]\n\n"
        except Exception as e:
            log.warning(f"[fastapi/chat_stream] generation failed for {cluster_id}: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': 'Chat generation failed'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/trending")
async def get_trending():
    cache_key = "api:trending"
    cached = cached_response(cache_key)
    if cached:
        return cached
        
    from trending import get_trending
    words = get_trending(limit=20)
    set_cache(cache_key, words, ttl=300)  # 5 minutes
    return words

@app.get("/api/cluster/{cluster_id}/share-card")
async def get_cluster_share_card(cluster_id: str):
    """Generates a high-quality social sharing image for a news cluster."""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    from urllib.parse import quote

    # 1. Fetch Data
    articles = db.execute(
        "SELECT title, original_title, is_translated, source, category FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", 
        (cluster_id,)
    )
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    s_row = db.execute_one(
        "SELECT summary, sentiment FROM cluster_summaries WHERE cluster_id = %s",
        (cluster_id,)
    )
    
    headline = _preferred_cluster_headline(articles)
    category = articles[0]["category"] or "ВЕСТИ"
    source_count = len(articles)
    source_names = []
    for article in articles:
        source = (article.get("source") or "").strip()
        if source and source not in source_names:
            source_names.append(source)
    source_preview = " · ".join(source_names[:3])
    if len(source_names) > 3:
        source_preview += " · +"
    share_date = datetime.datetime.now().strftime('%d.%m.%Y')

    bullets = []
    if s_row and s_row["summary"]:
        bullets = [
            re.sub(r'^(што се случува|заедничка линија|покриеност|што останува отворено)\s*:\s*', '', re.sub(r'^[-•*]\s*', '', line).strip(), flags=re.IGNORECASE)
            for line in s_row["summary"].split('\n')
            if line.strip() and not line.strip().lower().startswith('статии:')
        ]
        bullets = [cleanAndDecode(item) for item in bullets if item][:3]
    
    # 2. Image Config
    W, H = 1200, 630
    BG_COLOR = (15, 13, 12)
    PANEL_COLOR = (24, 21, 19)
    PANEL_ACCENT = (32, 38, 48)
    ACCENT_COLOR = (165, 197, 255)
    TEXT_COLOR = (242, 236, 226)
    MUTED_TEXT = (154, 143, 130)
    BORDER_COLOR = (51, 45, 41)
    
    img = Image.new("RGB", (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 3. Load Fonts
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
        font_reg_path = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        
        title_font = ImageFont.truetype(font_path, 58)
        kicker_font = ImageFont.truetype(font_path, 24)
        label_font = ImageFont.truetype(font_path, 20)
        body_font = ImageFont.truetype(font_reg_path, 30)
        footer_font = ImageFont.truetype(font_reg_path, 22)
    except:
        title_font = ImageFont.load_default()
        kicker_font = ImageFont.load_default()
        label_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        footer_font = ImageFont.load_default()

    # 4. Draw Layout
    padding = 72
    inner_x0, inner_y0 = padding - 18, padding - 12
    inner_x1, inner_y1 = W - padding + 18, H - padding + 12
    draw.rounded_rectangle((inner_x0, inner_y0, inner_x1, inner_y1), radius=28, fill=PANEL_COLOR, outline=BORDER_COLOR, width=2)
    draw.rounded_rectangle((inner_x0 + 24, inner_y0 + 24, inner_x1 - 24, inner_y0 + 86), radius=18, fill=PANEL_ACCENT)

    curr_y = padding + 8
    draw.text((padding + 18, curr_y), "ПРЕСЕК СУБЛИМАТ", font=label_font, fill=ACCENT_COLOR)

    badge_text = f"{source_count} ИЗВОРИ"
    badge_width = draw.textlength(badge_text, font=label_font) + 36
    badge_x0 = W - padding - badge_width
    badge_y0 = curr_y - 8
    draw.rounded_rectangle((badge_x0, badge_y0, badge_x0 + badge_width, badge_y0 + 38), radius=18, outline=ACCENT_COLOR, width=2)
    draw.text((badge_x0 + 18, curr_y), badge_text, font=label_font, fill=ACCENT_COLOR)

    curr_y += 72

    wrapped_title = textwrap.wrap(headline, width=34)
    for line in wrapped_title[:3]:
        draw.text((padding, curr_y), line, font=title_font, fill=TEXT_COLOR)
        curr_y += 68

    meta_y = curr_y + 6
    draw.text((padding, meta_y), category.upper(), font=kicker_font, fill=MUTED_TEXT)
    if source_preview:
        source_x = padding + draw.textlength(category.upper(), font=kicker_font) + 28
        draw.text((source_x, meta_y), source_preview, font=footer_font, fill=MUTED_TEXT)
    curr_y = meta_y + 52

    draw.line([(padding, curr_y), (W - padding, curr_y)], fill=BORDER_COLOR, width=2)
    curr_y += 28

    if bullets:
        for bullet in bullets[:2]:
            wrapped_bullet = textwrap.wrap(bullet, width=58)
            draw.text((padding, curr_y), "●", font=body_font, fill=ACCENT_COLOR)
            bullet_y = curr_y
            for line in wrapped_bullet[:2]:
                draw.text((padding + 38, bullet_y), line, font=body_font, fill=TEXT_COLOR)
                bullet_y += 38
            curr_y = bullet_y + 12
    else:
        fallback = f"Покриено од {source_count} извори, со сумиран контекст и споредба на аглите во известувањето."
        for line in textwrap.wrap(fallback, width=60)[:3]:
            draw.text((padding, curr_y), line, font=body_font, fill=MUTED_TEXT)
            curr_y += 38

    footer_y = H - padding + 6
    draw.text((padding, footer_y), "presek.live", font=kicker_font, fill=TEXT_COLOR)
    stats_str = f"{share_date}  ·  сподели ја веста како слика"
    draw.text((W - padding - draw.textlength(stats_str, font=footer_font), footer_y + 2), stats_str, font=footer_font, fill=MUTED_TEXT)

    # 5. Output
    out = BytesIO()
    img.save(out, format="PNG")
    safe_slug = re.sub(r"[^a-z0-9]+", "-", headline.lower()).strip("-")[:48] or cluster_id
    filename = f"presek-{safe_slug}-{cluster_id}.png"
    return Response(
        content=out.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
