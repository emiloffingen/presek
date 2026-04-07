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
import re
from typing import Optional, List
from collections import defaultdict
import urllib.request
import urllib.parse
import socket
import ipaddress
from pathlib import Path

import requests

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time, 
    cached_response, set_cache, delete_cache, is_balanced, assess_cluster_synthesis_freshness,
    annotate_cluster_articles, score_cluster_for_homepage, build_read_next_clusters,
    build_source_reputation_rows, build_editor_analytics_payload,
    event_stream, check_rate_limit,
)
from ai_engine import PROVIDERS, _call_ai_async, clean_json_response
from prompts import SYNTHESIS_SYSTEM_PROMPT
from config import (
    BREAKING_SCORE_THRESHOLD,
    API_MAX_PAGE,
    API_MAX_Q_LEN,
    CURATED_INTERNATIONAL_SOURCES,
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

validate_required_env()
app = FastAPI(title="Presek API 6.0", version="6.0.0")
_start_time = datetime.datetime.now(datetime.timezone.utc)
_APP_ROOT = Path(__file__).resolve().parent
_STATIC_ROOT = _APP_ROOT / "static"
_PROXY_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
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
    if clean in {"/api/chat_cluster", "/api/chat/stream"}:
        return True
    return bool(re.match(r"^/api/cluster/[a-f0-9]{6,64}/ask$", clean))


def _rate_limit_error_payload() -> dict:
    return {"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}


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
            response_text, _provider = await _call_ai_async(
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
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)

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
    if _is_rate_limited_path(request.url.path):
        client_host = str(getattr(getattr(request, "client", None), "host", "") or "0.0.0.0")
        if not check_rate_limit(client_host):
            return _apply_security_headers(JSONResponse(status_code=429, content=_rate_limit_error_payload()))

    response = await call_next(request)
    return _apply_security_headers(response)

@app.get("/api/health")
async def health():
    db_status = _probe_database()
    redis_status = _probe_redis()
    uptime_seconds = int((datetime.datetime.now(datetime.timezone.utc) - _start_time).total_seconds())
    overall = "ok" if (db_status["ok"] and redis_status["ok"]) else "degraded"
    return {
        "status": overall,
        "version": "6.0.0-async",
        "uptime_seconds": uptime_seconds,
        "database": db_status,
        "redis": redis_status,
    }


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

    row = db.execute_one("SELECT title FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,))
    count_row = db.execute_one("SELECT COUNT(*) FROM articles WHERE cluster_id = %s", (cluster_id,))

    title = row["title"] if row else "Вест"
    count = count_row["count"] if count_row and isinstance(count_row, dict) else (count_row[0] if count_row else 1)
    safe_title = title.replace("&", "&amp;").replace('"', "&quot;")
    if len(safe_title) > 65:
        line1 = safe_title[:65]
        line2 = safe_title[65:130] + ("..." if len(safe_title) > 130 else "")
    else:
        line1 = safe_title
        line2 = ""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a1a"/>
  <rect width="1200" height="10" y="0" fill="#E63946"/>
  <text x="80" y="120" font-family="serif" font-size="32" font-weight="800" fill="#E63946" letter-spacing="2">ПРЕСЕК АНАЛИЗА</text>
  <text x="80" y="240" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line1}</text>
  <text x="80" y="320" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line2}</text>
  <text x="80" y="520" font-family="sans-serif" font-size="28" fill="#aaaaaa">{count} извори анализирани во овој кластер</text>
  <text x="1120" y="560" font-family="serif" font-size="48" font-weight="bold" fill="#E63946" text-anchor="end">пресек.мк</text>
</svg>"""
    return Response(svg, media_type="image/svg+xml")


@app.get("/og-image.svg")
async def og_image():
    row = db.execute_one("SELECT COUNT(*) FROM articles")
    count = row["count"] if row and isinstance(row, dict) else (row[0] if row else 0)
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
async def get_profile_sync(token: str = Query(..., min_length=12, max_length=128)):
    row = db.execute_one(
        "SELECT profile_data, updated_at FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Synced profile not found")
    return {
        "status": "success",
        "token": token,
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
        "token": token,
        "profile": merged,
    }


@app.get("/api/profile/delivery")
async def get_profile_delivery(token: str = Query(..., min_length=12, max_length=128)):
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
        "token": token,
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
        "token": token,
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

@app.get("/api/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    """Returns detailed profile and relationships for an entity."""
    entity = db.execute_one("""
        SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score
        FROM knowledge_entities WHERE name = %s
    """, (name,))
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Get top relationships
    relationships = db.execute("""
        SELECT 
            CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
            weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC LIMIT 10
    """, (name, name, name))
    
    return {
        "profile": entity,
        "related": relationships
    }

@app.get("/api/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    """Returns the most mentioned entities."""
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

    return filtered


@app.get("/api/intelligence/international-curated")
async def get_international_curated(limit: int = 6):
    try:
        limit = min(12, max(1, int(limit)))
        cache_key = f"intl:curated:{limit}"
        cached = cached_response(cache_key, ttl=60)
        if cached:
            return cached

        rows = db.execute(
            """
            SELECT *
            FROM articles
            WHERE country != %s
              AND source = ANY(%s)
              AND created_at >= NOW() - INTERVAL '72 hours'
              AND (
                    is_translated = 1
                    OR (
                        COALESCE(original_title, '') <> ''
                        AND title <> original_title
                    )
                  )
            ORDER BY created_at DESC
            LIMIT 400
            """,
            ("🇲🇰", list(CURATED_INTERNATIONAL_SOURCES)),
        )

        clusters = defaultdict(list)
        for row in rows:
            if not _looks_macedonian_headline(row.get("title")):
                continue
            row["reading_time"] = calculate_reading_time(row.get("description", ""))
            clusters[row["cluster_id"]].append(row)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        ranked_clusters.sort(key=score_cluster, reverse=True)
        paged_clusters = ranked_clusters[:limit]

        cluster_ids = [cluster[0]["cluster_id"] for cluster in paged_clusters]
        synthesis_ids = db.get_synthesis_ids(cluster_ids) if cluster_ids else []
        metadata_rows = db.execute(
            "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
            (cluster_ids,),
        ) if cluster_ids else []
        rep_images = {row["cluster_id"]: row["representative_image"] for row in metadata_rows}

        result = []
        for arts in paged_clusters:
            cluster_score = score_cluster(arts)
            cid = arts[0]["cluster_id"]
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": arts[0].get("reading_time", 1),
                "score": round(cluster_score, 3),
                "is_breaking": cluster_score >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
            })

        payload = {
            "status": "success",
            "clusters": result,
            "total_clusters": len(ranked_clusters),
        }
        set_cache(cache_key, payload, ttl=60)
        return payload
    except Exception as e:
        log.error(f"[fastapi/intelligence/international-curated] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch curated international stories")

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
    try:
        # Fetch clusters with aggregated entity names
        sql = """
            WITH cluster_ents AS (
                SELECT cluster_id, array_agg(entity_name) as entity_names
                FROM cluster_entities
                GROUP BY cluster_id
            )
            SELECT a.*, COALESCE(ce.entity_names, '{}') as entity_names
            FROM (
        """
        params = []
        if q:
            sql += "SELECT * FROM articles WHERE 1=1 AND (title ILIKE %s OR description ILIKE %s) LIMIT 100"
            params = [f'%{q}%', f'%{q}%']
        elif entity:
            sql += """
                SELECT a.* FROM articles a
                JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id
                WHERE ce.entity_name = %s
                ORDER BY a.created_at DESC LIMIT 100
            """
            params = [entity]
        elif topic:
            sql += "SELECT * FROM articles WHERE topic = %s ORDER BY created_at DESC LIMIT 100"
            params = [topic]
        elif category:
            sql += "SELECT * FROM articles WHERE category = %s ORDER BY created_at DESC LIMIT 100"
            params = [category]
        else:
            sql += "SELECT * FROM articles WHERE country = '🇲🇰' ORDER BY created_at DESC LIMIT 200"

        rows = db.execute(sql + ") a LEFT JOIN cluster_ents ce ON a.cluster_id = ce.cluster_id", tuple(params))

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
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", [])
            })

        return {
            "status": "success",
            "clusters": result,
            "page": page,
            "has_more": len(ranked_clusters) > start + page_size
        }
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
            "SELECT summary, perspectives, created_at FROM cluster_summaries WHERE cluster_id = %s", 
            (cluster_id,)
        )
        synthesis = s_row["summary"] if s_row else None
        
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
            perspectives = json.loads(perspectives)
        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))

        # 3. Fetch metadata (tags, etc)
        m_row = db.execute_one(
            "SELECT tags, topics FROM cluster_metadata WHERE cluster_id = %s", 
            (cluster_id,)
        )
        tags = filter_cluster_tags(m_row["tags"] if m_row else [])
        topics = m_row["topics"] if m_row else []

        # 4. Related clusters
        related = []
        if tags:
            related_rows = db.execute("""
                WITH cluster_ents AS (
                    SELECT cluster_id, array_agg(entity_name) as entity_names
                    FROM cluster_entities
                    GROUP BY cluster_id
                )
                SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags, COALESCE(ce.entity_names, '{}') as entity_names
                FROM articles a
                LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
                LEFT JOIN cluster_ents ce ON a.cluster_id = ce.cluster_id
                WHERE a.cluster_id != %s
                  AND a.created_at >= NOW() - INTERVAL '72 hours'
                  AND (
                    m.tags && %s
                    OR EXISTS (
                        SELECT 1 FROM cluster_entities ce2
                        WHERE ce2.cluster_id = a.cluster_id
                          AND ce2.entity_name = ANY(%s)
                    )
                  )
                ORDER BY a.created_at DESC
                LIMIT 120
            """, (cluster_id, tags, list({entity for article in articles for entity in (article.get("entity_names") or [])})))
            related = build_read_next_clusters(cluster_id, articles, tags, related_rows, limit=4)

        return {
            "status": "success",
            "data": {
                "cluster_id": cluster_id,
                "articles": articles,
                "synthesis": synthesis,
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
        log.error(f"FastAPI Cluster Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cluster detail")


@app.post("/api/cluster/{cluster_id}/ask")
async def ask_cluster(cluster_id: str, request: Request):
    """Answers a question using only the current cluster's context."""
    try:
        try:
            try:
                payload = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            question = str((payload or {}).get("question") or "").strip()
            return await _build_cluster_answer_payload(cluster_id, question)
        except HTTPException:
            raise
    except HTTPException:
        raise


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
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
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
            "  AND (country = '🇲🇰' OR country IS NULL OR country = '') "
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
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
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
        if ".." in url:
            return _error_json("Blocked URL", 403)
        content_type = "image/jpeg"
        if url.endswith(".svg"):
            content_type = "image/svg+xml"
        elif url.endswith(".png"):
            content_type = "image/png"
        elif url.endswith(".webp"):
            content_type = "image/webp"
        try:
            full_path = os.path.join(os.getcwd(), url.lstrip("/"))
            if not os.path.exists(full_path):
                return _error_json("Local file not found", 404)
            with open(full_path, "rb") as handle:
                return Response(handle.read(), media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
        except Exception as e:
            return _error_json(f"Failed to serve local file: {e}", 500)

    if not re.match(r'^https?://', url):
        return _error_json("Invalid URL scheme", 400)

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
            return _error_json("Failed to fetch image", response.status_code)

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in _PROXY_ALLOWED_TYPES:
            return _error_json("Unsupported content type", 415)

        image_data = b""
        for chunk in response.iter_content(chunk_size=8192):
            image_data += chunk
            if len(image_data) > _PROXY_MAX_BYTES:
                return _error_json("Image too large", 413)

        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(image_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > target_width:
            ratio = target_width / float(img.width)
            img = img.resize((target_width, int(float(img.height) * ratio)), Image.Resampling.LANCZOS)

        webp_io = BytesIO()
        quality = 20 if target_width <= 50 else 80
        img.save(webp_io, "WEBP", quality=quality, method=6)
        optimized_data = webp_io.getvalue()

        set_cache(cache_key, {"data": optimized_data.hex(), "content_type": "image/webp"}, ttl=86400)
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
            generator = await _call_ai_async(full_prompt, SYNTHESIS_SYSTEM_PROMPT, task_type="chat", stream=True)
            if generator:
                async for chunk in generator:
                    if chunk:
                        yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': 'Chat generation failed'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/trending")
async def get_trending():
    from trending import get_trending
    words = get_trending(limit=20)
    return words
