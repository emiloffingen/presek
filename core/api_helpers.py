"""
api_helpers.py — Shared helpers used by the FastAPI backend and background tasks.

Keeping these in one place ensures bug fixes and behavioural changes apply everywhere.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
from threading import Lock
from typing import Optional

log = logging.getLogger("presek.api.helpers")

# Simple thread-safe DNS cache for is_safe_url to reduce redundant network lookups
_dns_cache = {}
_dns_cache_lock = Lock()
DNS_CACHE_TTL = 300  # 5 minutes


def _get_cached_addrinfo(hostname):
    now = time.time()
    with _dns_cache_lock:
        if hostname in _dns_cache:
            result, timestamp = _dns_cache[hostname]
            if now - timestamp < DNS_CACHE_TTL:
                return result
            else:
                del _dns_cache[hostname]
    return None


def _set_cached_addrinfo(hostname, addr_infos):
    with _dns_cache_lock:
        # Prevent unbounded growth
        if len(_dns_cache) > 1000:
            _dns_cache.clear()
        _dns_cache[hostname] = (addr_infos, time.time())


def is_safe_url(url: str) -> bool:
    """Rigorous SSRF protection: block local/private network ranges and DNS rebinding."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Strip port if present
    hostname_only = hostname.split(":")[0].lower()

    # 1. Direct block for common local hostnames (case-insensitive)
    BLOCKED_HOSTNAMES = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "0:0:0:0:0:0:0:1",
        "metadata",
        "metadata.google.internal",
        "metadata.internal",
        "169.254.169.254",
        "fd00:ec2::254",
        "169.254.170.2",
        "100.100.100.200",
    }
    if hostname_only in BLOCKED_HOSTNAMES:
        return False

    # 2. Block IP-like hostnames
    if hostname_only.replace(".", "").replace(":", "").isdigit() or all(
        c in "0123456789abcdefABCDEF:." for c in hostname_only
    ):
        try:
            ip_address = ipaddress.ip_address(hostname_only)
            if ip_address.is_private or ip_address.is_loopback or ip_address.is_link_local or ip_address.is_reserved:
                return False
        except ValueError:
            pass

    # 3. Resolve hostname and check all resolved IPs (DNS rebinding protection)
    try:
        addr_infos = _get_cached_addrinfo(hostname)
        if addr_infos is None:
            addr_infos = socket.getaddrinfo(hostname, None)
            if addr_infos:
                _set_cached_addrinfo(hostname, addr_infos)

        if not addr_infos:
            return False

        for addr_info in addr_infos:
            ip = addr_info[4][0]
            try:
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                    return False
            except ValueError:
                continue

        # 4. Additional DNS-based checks for cloud metadata
        metadata_markers = [
            "metadata.",
            ".metadata",
            "metadata.google",
            "metadata.internal",
            "169.254.",
            "fd00:ec2",
            "100.100.100.",
        ]
        if any(marker in hostname for marker in metadata_markers):
            return False

        return True
    except Exception as e:
        log.error(f"is_safe_url error for {hostname}: {e}")
        return False


_EXTRA_NOISE = {"vesti", "vest", "izvor", "izvori", "klaster"}
_GENERIC_ANGLES = {"perspektiva", "ugao", "tacka", "stav", "glediste", "агол", "гледиште", "став"}
_SAFE_TOPIC_RE = re.compile(r"[^A-Za-z0-9._-]+")

_BACKEND_I18N = {
    "sr": {
        "angle.different": "razliciti akcenti",
        "angle.common": "zajednicka linija",
        "angle.unclear": "Sta ostaje otvoreno",
        "angle.reaction": "reakcije i odgovori",
        "angle.context": "siri kontekst",
        "angle.key": "Kljucan ugao",
        "q.development": "Sta je glavni razvoj u ovoj prici?",
        "q.differences": "Kako se razlikuju izvori u izvestaju?",
        "q.unconfirmed": "Sta jos uvek nije potvrdeno?",
        "q.next": "Sta slede dalje u ovoj prici?",
        "q.important": "Sta je najvaznija vest u ovoj prici?",
        "q.category_dev": "Koji je najvazniji razvoj u temi {cat}?",
    },
    "mk": {
        "angle.different": "различни акценти",
        "angle.common": "заедничка линија",
        "angle.unclear": "Што останува отворено",
        "angle.reaction": "реакции и одговори",
        "angle.context": "поширок контекст",
        "angle.key": "Клучен агол",
        "q.development": "Што е главниот развој во оваа приказна?",
        "q.differences": "Како се разликуваат изворите во извештајот?",
        "q.unconfirmed": "Што сè уште не е потврдено?",
        "q.next": "Што следува понатаму во оваа приказна?",
        "q.important": "Што е најважната вест во оваа вест?",
        "q.category_dev": "Кој е најважниот развој во темата {cat}?",
    }
}

def _clean_text_block(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "")
    text = re.sub(r"^\s*(summary|rezime|sublimat|clanci)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[•*\-\u2022]+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _infer_perspective_angle(content: str, lang: str = "sr", fallback: str = None) -> str:
    lowered = content.lower()
    L = _BACKEND_I18N.get(lang, _BACKEND_I18N["sr"])
    fallback = fallback or L["angle.key"]
    
    if any(token in lowered for token in ("razlik", "akcenat", "formulac", "naglas", "разлик", "акцент")):
        return L["angle.different"]
    if any(token in lowered for token in ("zajednick", "vecina izvori", "ista linija", "svi izvori", "заедничк", "иста линија")):
        return L["angle.common"]
    if any(token in lowered for token in ("otvoreno", "nejasno", "nepotvrdeno", "jos uvek ne", "ostaje", "отворено", "нејасно", "непотврдено")):
        return L["angle.unclear"]
    if any(token in lowered for token in ("reakcija", "odgovor", "komentar", "osuda", "реакција", "одговор")):
        return L["angle.reaction"]
    if any(token in lowered for token in ("kontekst", "pozadina", "siri", "контекст", "позадина", "поширок")):
        return L["angle.context"]
    return fallback


def normalize_summary_text(raw_summary) -> str:
    if not raw_summary:
        return ""

    from nlp.utils import extract_clean_summary_text

    if isinstance(raw_summary, list):
        cleaned_lines = [extract_clean_summary_text(line) for line in raw_summary]
        return "\n".join(f"• {_clean_text_block(line)}" for line in cleaned_lines if _clean_text_block(line))

    text = extract_clean_summary_text(str(raw_summary).replace("\r", "\n"))
    lines = []
    seen = set()

    for raw_line in text.split("\n"):
        clean = _clean_text_block(raw_line)
        if not clean:
            continue
        if clean.lower() == "clanci:":
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(clean)

    if not lines:
        return ""

    if len(lines) == 1:
        return lines[0]

    return "\n".join(f"• {line}" for line in lines[:4])


def normalize_perspectives(raw_perspectives, lang: str = "sr") -> list[dict]:
    """
    Normalise a raw perspectives value into a clean list of {angle, content} dicts.

    Accepts:
    - A JSON string (decoded first)
    - A list of dicts (with flexible key names: angle/label/title/name, content/text/description)
    - A list of plain strings
    """
    if not raw_perspectives:
        return []
    if isinstance(raw_perspectives, str):
        try:
            raw_perspectives = json.loads(raw_perspectives)
        except Exception as e:
            log.warning(f"Failed to parse perspectives JSON: {e}")
            return []
    if not isinstance(raw_perspectives, list):
        return []

    result = []
    seen = set()
    L = _BACKEND_I18N.get(lang, _BACKEND_I18N["sr"])
    
    leaked_indicators = {
        "verification_report", "agreements", "conflicts", "missing_info",
        "sentiment", "tone_analysis", "synthetic_headline", "synthetic_standfirst",
        "key_facts", "pluralism_score", "narrative_diversity", "analyst_entities"
    }

    for item in raw_perspectives:
        if isinstance(item, str):
            content = _clean_text_block(item)
            if content:
                lowered_content = content.lower()
                if any(ind in lowered_content for ind in leaked_indicators):
                    continue
                angle = _infer_perspective_angle(content, lang=lang)
                key = content.casefold()
                if key not in seen:
                    seen.add(key)
                    result.append({"angle": angle, "content": content})
            continue
        if not isinstance(item, dict):
            continue
        angle = _clean_text_block(item.get("angle") or item.get("label") or item.get("title") or item.get("name") or "")
        content = _clean_text_block(item.get("content") or item.get("text") or item.get("description") or "")
        if not content:
            continue
        lowered_content = content.lower()
        if any(ind in lowered_content for ind in leaked_indicators):
            continue
        lowered_angle = angle.lower()
        if any(ind in lowered_angle for ind in leaked_indicators):
            continue
        if not angle or angle.casefold() in _GENERIC_ANGLES:
            angle = _infer_perspective_angle(content, lang=lang)
        key = content.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append({"angle": angle or L["angle.key"], "content": content})

    return result[:4]


def normalize_citation_sources(raw_sources) -> list[dict]:
    """Normalize stored citation-source rows into a stable ordered list."""
    if not raw_sources:
        return []
    if isinstance(raw_sources, str):
        try:
            raw_sources = json.loads(raw_sources)
        except Exception as e:
            log.debug(f"Failed to parse citation sources JSON: {e}")
            return []
    if not isinstance(raw_sources, list):
        return []

    result = []
    for idx, item in enumerate(raw_sources, start=1):
        if not isinstance(item, dict):
            continue
        source = _clean_text_block(item.get("source"))
        title = _clean_text_block(item.get("title"))
        link = str(item.get("link") or "").strip()[:2048]
        created_at = str(item.get("created_at") or "").strip()[:64]
        category = _clean_text_block(item.get("category"))
        if not source and not title:
            continue
        result.append(
            {
                "index": idx,
                "source": source,
                "title": title,
                "link": link,
                "created_at": created_at,
                "category": category,
            }
        )
    return result[:8]


def normalize_server_delivery_subscription(payload) -> dict:
    payload = payload or {}
    raw_channel = str(payload.get("channel") or "ntfy").strip().lower()
    channel = raw_channel if raw_channel == "webpush" else "ntfy"

    raw_target = str(payload.get("target") or "").strip()

    if channel == "ntfy":
        target = _SAFE_TOPIC_RE.sub("-", raw_target).strip("-._")[:120]
    else:
        # WebPush target is a JSON string of the PushSubscription object
        target = raw_target[:2048]

    is_active = bool(payload.get("isActive")) and bool(target)

    return {
        "channel": channel,
        "target": target,
        "morningBriefing": payload.get("morningBriefing") is not False,
        "weeklyDigest": bool(payload.get("weeklyDigest")),
        "breakingTopics": bool(payload.get("breakingTopics")),
        "breakingSources": bool(payload.get("breakingSources")),
        "isActive": is_active,
    }


def default_related_questions(question: str, category: Optional[str] = None, lang: str = "sr") -> list[str]:
    L = _BACKEND_I18N.get(lang, _BACKEND_I18N["sr"])
    fallback = [
        L["q.development"],
        L["q.differences"],
        L["q.unconfirmed"],
    ]
    if category:
        fallback[0] = L["q.category_dev"].format(cat=str(category).lower())
    return [q for q in fallback if q.strip() and q.strip() != question.strip()][:3]


def related_questions_from_context(
    question: str,
    category: Optional[str] = None,
    *,
    has_perspectives: bool = False,
    has_multiple_sources: bool = False,
    has_unclear_points: bool = False,
    lang: str = "sr",
) -> list[str]:
    L = _BACKEND_I18N.get(lang, _BACKEND_I18N["sr"])
    suggestions = []
    lowered = (question or "").strip().lower()

    def add(text: str):
        text = str(text or "").strip()
        if text and text.casefold() != lowered and text not in suggestions:
            suggestions.append(text)

    if not any(token in lowered for token in ("razliku", "izvor", "perspektive", "разлик", "извор", "перспектива")) and (
        has_perspectives or has_multiple_sources
    ):
        add(L["q.differences"])
    if not any(token in lowered for token in ("nejasno", "nepotvrdeno", "otvoreno", "нејасно", "непотврдено", "отворено")):
        add(L["q.unconfirmed"])
    if not any(token in lowered for token in ("sledece", "dalje", "posledice", "reakcija", "следува", "понатаму", "последица", "реакција")):
        add(L["q.next"])
    if has_multiple_sources and not any(token in lowered for token in ("najvazniji", "novo", "glavno", "најважно", "ново", "главно")):
        add(L["q.important"])

    for item in default_related_questions(question, category, lang=lang):
        add(item)

    if has_unclear_points:
        add(L["q.unconfirmed"])

    return suggestions[:3]


def text_terms(text: str) -> set[str]:
    from nlp.keywords import TAG_NOISE_WORDS

    terms = re.findall(r"[A-Za-z0-9]{3,}", (text or "").lower())
    return {t for t in terms if t not in TAG_NOISE_WORDS and t not in _EXTRA_NOISE}


def build_citation_snippet(article):
    from nlp import summarize_locally

    title = str((article or {}).get("title") or "").strip()
    description = str((article or {}).get("description") or "").strip()
    if description:
        snippet = summarize_locally(description, sentence_count=1)
        if snippet:
            return snippet.strip()[:220]
    return title[:220]


def rank_cluster_citations(
    question: str,
    answer: str,
    articles: list[dict],
    preferred_numbers: list,
) -> list[dict]:
    from utils import build_cluster_source_signals, get_source_trust_label

    question_terms = text_terms(question)
    answer_terms = text_terms(answer)
    combined_terms = question_terms | answer_terms

    preferred_order = []
    for raw in preferred_numbers or []:
        try:
            idx = int(raw)
        except Exception as e:
            log.debug(f"Failed to parse preferred number {raw}: {e}")
            continue
        if idx not in preferred_order:
            preferred_order.append(idx)

    source_signals = build_cluster_source_signals(articles)
    signal_by_key = {}
    for article, signal in zip(articles, source_signals):
        key = (
            str(article.get("source") or ""),
            str(article.get("title") or ""),
            str(article.get("link") or ""),
        )
        signal_by_key[key] = signal

    ranked = []
    for idx, article in enumerate(articles, start=1):
        article_text = " ".join(
            [
                str(article.get("title") or ""),
                str(article.get("description") or ""),
                str(article.get("source") or ""),
            ]
        )
        article_terms = text_terms(article_text)
        overlap = len(combined_terms & article_terms)
        preferred_bonus = 5 if idx in preferred_order else 0
        title_bonus = 1 if question_terms & text_terms(str(article.get("title") or "")) else 0
        trust_bonus = 1 if get_source_trust_label(str(article.get("source") or "")) == "Visoko poverenje" else 0
        signal = (
            signal_by_key.get(
                (
                    str(article.get("source") or ""),
                    str(article.get("title") or ""),
                    str(article.get("link") or ""),
                )
            )
            or {}
        )
        ranked.append(
            (
                preferred_bonus + overlap + title_bonus + trust_bonus,
                -idx,
                {
                    "source": article.get("source"),
                    "title": article.get("title"),
                    "link": article.get("link"),
                    "created_at": article.get("created_at"),
                    "snippet": build_citation_snippet(article),
                    "trust_label": signal.get("trust_label")
                    or get_source_trust_label(str(article.get("source") or "")),
                    "role_label": signal.get("role_label", ""),
                },
            )
        )

    ranked.sort(reverse=True)
    top = [item[2] for item in ranked if item[0] > 0]
    if top:
        return top[:3]
    return [
        {
            "source": article.get("source"),
            "title": article.get("title"),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "snippet": build_citation_snippet(article),
            "trust_label": get_source_trust_label(str(article.get("source") or "")),
            "role_label": "",
        }
        for article in articles[:2]
    ]
