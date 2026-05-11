import datetime
import math
import re
import json
import time
from typing import List, Dict, Any
import logging
from config import BALANCED_COVERAGE_THRESHOLD, DEFAULT_CREDIBILITY
from utils.cache import redis_client
from utils.db_helpers import get_source_registry
from utils.time import _coerce_datetime

log = logging.getLogger("presek")

_SOURCE_STATUS_CACHE = {"time": 0.0, "data": {}}

def get_source_health_map(ttl: int = 60) -> Dict[str, Any]:
    now = time.time()
    if _SOURCE_STATUS_CACHE["data"] and now - _SOURCE_STATUS_CACHE["time"] < ttl:
        return _SOURCE_STATUS_CACHE["data"]
    try:
        raw = redis_client.hgetall("presek:source_statuses") or {}
        parsed = {k: json.loads(v) for k, v in raw.items()}
        _SOURCE_STATUS_CACHE.update({"time": now, "data": parsed})
        return parsed
    except Exception as e:
        log.debug(f"Failed to load source statuses: {e}")
        return _SOURCE_STATUS_CACHE["data"] or {}

def get_source_quality_multiplier(source: str) -> float:
    status = get_source_health_map().get(source) or {}
    q_score = status.get("quality_score")
    if q_score is None:
        return 1.0
    return max(0.45, min(1.05, 0.55 + float(q_score) * 0.5))

def get_source_effective_weight(source: str) -> float:
    reg = get_source_registry()
    base = reg.get(source, {}).get("credibility", DEFAULT_CREDIBILITY)
    return base * get_source_quality_multiplier(source)

def get_source_trust_label(source: str) -> str:
    weight = get_source_effective_weight(source)
    if weight >= 1.75:
        return "Visoko poverenje"
    if weight >= 1.3:
        return "Potvrden izvor"
    return "sledeci izvor"

def _cluster_title_overlap(left: str, right: str) -> float:
    l_set = {t for t in str(left or "").lower().split() if len(t) >= 4}
    r_set = {t for t in str(right or "").lower().split() if len(t) >= 4}
    union = len(l_set | r_set) or 1
    return len(l_set & r_set) / union

def build_cluster_source_signals(arts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = rank_articles_in_cluster(arts)
    if not ranked:
        return []

    lead_title = str(ranked[0].get("title") or "")
    lead_dt = _coerce_datetime(ranked[0].get("created_at"))
    earliest_dt = min(
        (
            _coerce_datetime(a.get("created_at"))
            for a in ranked
            if _coerce_datetime(a.get("created_at"))
        ),
        default=None,
    )

    corrob_scores = []
    for art in ranked:
        t = str(art.get("title") or "")
        corrob_scores.append(
            sum(
                1
                for o in ranked
                if o is not art
                and _cluster_title_overlap(t, str(o.get("title") or "")) >= 0.3
            )
        )

    signals = []
    reg = get_source_registry()
    for idx, art in enumerate(ranked):
        src = str(art.get("source") or "")
        weight = get_source_effective_weight(src)
        art_dt = _coerce_datetime(art.get("created_at"))
        overlap = (
            1.0
            if idx == 0
            else _cluster_title_overlap(str(art.get("title") or ""), lead_title)
        )
        corrob_by = corrob_scores[idx]

        if idx == 0 and corrob_by >= 2:
            role, note, tone = (
                "Najpotvrden izvor",
                "Ovoj izvor me nosi glavnata linija sto me potvrduvaat i povece drugi redakcii.",
                "confirm",
            )
        elif idx == 0 and weight >= 1.6:
            role, note, tone = (
                "Vodecki doverliv izvor",
                "Ovoj izvor stoi najvisoko po doverba i me dava najcelosnata vodecka ramka.",
                "lead",
            )
        elif art_dt and earliest_dt and art_dt <= earliest_dt and weight >= 1.3:
            role, note, tone = (
                "Prv izvestaj",
                "Ovoj izvor bil medju prvite sto ga objavile razvojot.",
                "lead",
            )
        elif overlap < 0.22:
            role, note, tone = (
                "Razlicen ugao",
                "Ovoj izvor me otvora prikaznata od drug aspekt, a ne samo me povtoruva vodeckata linija.",
                "contrast",
            )
        elif art_dt and lead_dt and art_dt > lead_dt + datetime.timedelta(minutes=90):
            role, note, tone = (
                "Sledenje / reakcija",
                "Ovoj izvor doadja podocna i povece nosi reakcija, posledica ili follow-up.",
                "context",
            )
        else:
            role, note, tone = (
                "Dopolnuva kontekst",
                "Ovoj izvor me potvrduva glavnata prica, no dodava i svoj kontekst ili detali.",
                "confirm" if overlap >= 0.4 else "context",
            )

        signals.append(
            {
                "role_label": role,
                "role_note": note,
                "role_tone": tone,
                "trust_label": get_source_trust_label(src),
                "source_category": reg.get(src, {}).get("category", "Lokalni"),
                "effective_weight": round(weight, 3),
                "corroborated_by": corrob_by,
            }
        )
    return signals

def annotate_cluster_articles(
    arts: List[Dict[str, Any]], prefer_recent: bool = False
) -> List[Dict[str, Any]]:
    ranked = rank_articles_in_cluster(arts, prefer_recent=prefer_recent)
    signals = build_cluster_source_signals(ranked)

    TIER_MAP = {
        "Agencijski": "M",
        "Javni servis": "M",
        "glavni": "M",
        "Nezavisni": "I",
        "Istraživački": "I",
        "Regionalni": "R",
        "Alternativni": "R",
        "Lokalni": "R",
    }
    reg = get_source_registry()
    tiers = {
        TIER_MAP.get(reg.get(a["source"], {}).get("category", "Lokalni"), "R")
        for a in ranked
    }

    bal_score = len(tiers)
    bal_label = (
        "sirok Konsenzus"
        if bal_score >= 3
        else ("Raznovidni izvori" if bal_score == 2 else None)
    )

    annotated = []
    lead = ranked[0] if ranked else None
    for idx, (art, sig) in enumerate(zip(ranked, signals)):
        enriched = {
            **art,
            "source_signal": sig,
            "coverage_balance": {"score": bal_score, "label": bal_label},
        }
        if idx == 0:
            enriched["relationship_to_lead"] = {
                "tone": "lead",
                "label": "OSNOVNA OBJAVA",
            }
        else:
            overlap = _cluster_title_overlap(
                lead.get("title", ""), art.get("title", "")
            )
            label = (
                "ISTA prica"
                if overlap >= 0.45
                else ("POVRZANA prica" if overlap >= 0.20 else "IST kontekst")
            )
            enriched["relationship_to_lead"] = {"tone": "neutral", "label": label}
        annotated.append(enriched)
    return annotated

def rank_articles_in_cluster(
    arts: List[Dict[str, Any]], prefer_recent: bool = False
) -> List[Dict[str, Any]]:
    if not arts:
        return []

    def initial_weight(a):
        w = get_source_effective_weight(a["source"]) + (
            0.12 if str(a.get("description") or "").strip() else 0.0
        )
        if prefer_recent:
            return (
                _coerce_datetime(a.get("created_at")) or datetime.datetime.min
            ).timestamp() + (w * 0.001)
        return w

    sorted_arts = sorted(arts, key=initial_weight, reverse=True)
    ranked = []
    seen_titles = []
    for art in sorted_arts:
        t = str(art.get("title") or "").strip()
        is_red = any(_cluster_title_overlap(t, prev) >= 0.85 for prev in seen_titles)
        ranked.append({**art, "is_redundant": is_red})
        if not is_red:
            seen_titles.append(t)

    def final_key(a):
        penalty = -5.0 if a.get("is_redundant") else 0.0
        w = get_source_effective_weight(a["source"])
        dt = _coerce_datetime(a.get("created_at")) or datetime.datetime.min
        return (penalty, dt, w) if prefer_recent else (penalty + w, dt)

    return sorted(ranked, key=final_key, reverse=True)

def build_read_next_clusters(
    cur_id: str,
    cur_arts: List[Dict[str, Any]],
    cur_tags: List[str],
    candidates: List[Dict[str, Any]],
    limit: int = 4,
) -> List[Dict[str, Any]]:
    cur_ranked = annotate_cluster_articles(cur_arts or [])
    if not cur_ranked:
        return []

    c_tags = {str(t).strip() for t in (cur_tags or []) if str(t).strip()}
    c_ents = {
        str(e).strip()
        for a in cur_ranked
        for e in (a.get("entity_names") or [])
        if str(e).strip()
    }
    c_topics = {
        str(a.get("topic")).strip() for a in cur_ranked if str(a.get("topic")).strip()
    }
    c_lead_title = str(cur_ranked[0].get("title") or "")

    grouped = {}
    for r in candidates or []:
        cid = r.get("cluster_id")
        if cid and cid != cur_id:
            grouped.setdefault(cid, []).append(r)

    results = []
    for cid, rows in grouped.items():
        ranked = annotate_cluster_articles(rows)
        if not ranked:
            continue
        lead = ranked[0]
        cand_tags = {
            str(t).strip()
            for r in rows
            for t in (r.get("cluster_tags") or [])
            if str(t).strip()
        }
        cand_ents = {
            str(e).strip()
            for r in rows
            for e in (r.get("entity_names") or [])
            if str(e).strip()
        }
        cand_topics = {
            str(r.get("topic")).strip() for r in rows if str(r.get("topic")).strip()
        }

        sh_tags, sh_ents, sh_topics = (
            c_tags & cand_tags,
            c_ents & cand_ents,
            c_topics & cand_topics,
        )
        overlap = _cluster_title_overlap(c_lead_title, str(lead.get("title") or ""))

        score = 0.0
        label, note = "Ist kontekst", "Povrzan klaster so slicen novinarski kontekst."

        if sh_ents and overlap >= 0.25:
            score += 2.0 + len(sh_ents) * 0.22
            label, note = (
                "Sleden razvoj",
                "Istite akteri ili tema, no so nov razvoj ili sledna faza.",
            )
        elif sh_tags and overlap < 0.22:
            score += 1.6 + len(sh_tags) * 0.18
            label, note = "pozadina i kontekst", "Ja siri slikata so povrzan kontekst."
        elif sh_ents:
            score += 1.35 + len(sh_ents) * 0.15
            label, note = (
                "Isti akteri, drug ugao",
                "Gi vrzuva istite iminja, no od poinakov ugao.",
            )
        elif sh_topics:
            score += 1.05 + len(sh_topics) * 0.12
        else:
            continue

        if lead.get("source_signal", {}).get("trust_label") == "Visoko poverenje":
            score += 0.35
        dt = _coerce_datetime(lead.get("created_at"))
        if dt:
            score += max(
                0.0,
                0.8
                - min(
                    0.8, (datetime.datetime.now() - dt).total_seconds() / 3600.0 * 0.08
                ),
            )

        if score > 0.9:
            results.append(
                {
                    "cluster_id": cid,
                    "title": lead.get("title"),
                    "image_url": lead.get("image_url"),
                    "relationship_label": label,
                    "relationship_note": note,
                    "shared_tags": sorted(sh_tags)[:3],
                    "shared_entities": sorted(sh_ents)[:3],
                    "shared_topics": sorted(sh_topics)[:2],
                    "source": lead.get("source"),
                    "created_at": lead.get("created_at"),
                    "score": round(score, 3),
                }
            )

    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]

def build_source_reputation_rows(
    source_rows, pulse_rows=None, speed_rows=None, history_rows=None, category_rows=None
):
    pulse_map = {
        str(i.get("source")): int(i.get("count") or i.get("n") or 0)
        for i in (pulse_rows or [])
    }
    speed_map = {
        str(i.get("source")): int(i.get("first_count") or 0) for i in (speed_rows or [])
    }
    history_map = {str(i.get("source")): i for i in (history_rows or [])}

    from collections import defaultdict

    cat_map = defaultdict(list)
    for cr in category_rows or []:
        s = str(cr.get("source") or "")
        if s and len(cat_map[s]) < 3:
            cat_map[s].append(cr["category"])

    results = []
    for row in source_rows or []:
        name = str(row.get("name") or row.get("source") or "").strip()
        if not name:
            continue
        weight = get_source_effective_weight(name)
        hist = history_map.get(name, {})
        l_30d = int(hist.get("lead_count_30d") or 0)
        c_rate = (
            round(int(hist.get("corroborated_lead_count_30d") or 0) / l_30d, 2)
            if l_30d > 0
            else 0.0
        )
        l_rate = (
            round(int(hist.get("solo_lead_count_30d") or 0) / l_30d, 2)
            if l_30d > 0
            else 0.0
        )
        vol_7d = int(hist.get("recent_7d_volume") or 0)
        delta = vol_7d - int(hist.get("previous_7d_volume") or 0)
        first_c = speed_map.get(name, 0)

        results.append(
            {
                "source": name,
                "country": row.get("country") or "",
                "category": row.get("category") or "",
                "top_categories": cat_map.get(name, []),
                "effective_weight": round(weight, 2),
                "trust_tier": (
                    "Visoko poverenje"
                    if weight >= 1.75
                    else ("Potvrden izvor" if weight >= 1.3 else "sledeci izvor")
                ),
                "recent_volume": pulse_map.get(name, 0),
                "speed_first_count": first_c,
                "corroboration_rate": c_rate,
                "lone_lead_rate": l_rate,
                "lead_count_30d": l_30d,
                "trend_label": (
                    "Raste" if delta >= 4 else ("Slabee" if delta <= -4 else "Stabilen ritam")
                ),
                "tendency": (
                    "Cesto prv na prikaznata" if first_c >= 5 else "Postepeno sledenje"
                ),
                "last_fetched": row.get("last_fetched"),
                "is_active": row.get("is_active", True),
            }
        )
    return sorted(
        results,
        key=lambda i: (
            i["effective_weight"],
            i["recent_volume"],
            i["speed_first_count"],
        ),
        reverse=True,
    )

def build_editor_analytics_payload(
    profile_stats=None,
    delivery_stats=None,
    top_topics=None,
    top_sources=None,
    tracking_stats=None,
    tracking_perf=None,
    sugg_surface=None,
    sugg_kind=None,
    sugg_period=None,
):
    p, d, t = (profile_stats or {}), (delivery_stats or {}), (tracking_stats or {})
    s7, o7 = (
        int(t.get("sends_7d") or 0),
        int(t.get("opens_7d") or 0),
    )

    def _perf(rows, kind_map):
        res = []
        for r in rows or []:
            k = str(r.get("delivery_kind") or r.get("suggestion_kind") or "")
            if not k:
                continue
            s, o, c = (
                int(r.get("sends") or r.get("impressions") or 0),
                int(r.get("opens") or r.get("follows") or 0),
                int(r.get("clicks") or r.get("dismissals") or 0),
            )
            res.append(
                {
                    "kind": k,
                    "label": kind_map.get(k, k),
                    "sends": s,
                    "opens": o,
                    "clicks": c,
                    "rate": round((o / s) * 100, 1) if s else 0.0,
                }
            )
        return sorted(res, key=lambda x: x["rate"], reverse=True)

    s_perf = []
    p_map = {r.get("surface"): r for r in (sugg_period or [])}
    for r in sugg_surface or []:
        surf = r.get("surface")
        curr = p_map.get(surf, {})
        rate = round(
            int(r.get("follows") or 0) / int(r.get("impressions") or 1) * 100, 1
        )
        prev_rate = round(
            int(curr.get("previous_follows") or 0)
            / int(curr.get("previous_impressions") or 1)
            * 100,
            1,
        )
        s_perf.append(
            {
                **r,
                "label": {"onboarding": "Vodic", "cluster": "klaster"}.get(surf, surf),
                "conversion_rate": rate,
                "trend_delta": round(rate - prev_rate, 1),
            }
        )

    return {
        "synced_profiles": int(p.get("synced_profiles") or 0),
        "delivery_active": int(d.get("delivery_active") or 0),
        "sends_7d": s7,
        "open_rate_7d": round((o7 / s7) * 100, 1) if s7 else 0.0,
        "delivery_performance": _perf(
            tracking_perf, {"morning": "Utrinski", "weekly": "Nedelen"}
        ),
        "suggestion_performance": sorted(
            s_perf, key=lambda x: x["conversion_rate"], reverse=True
        ),
        "top_topics": [
            {"topic": r.get("topic"), "n": int(r.get("n") or 0)}
            for r in (top_topics or [])
        ],
        "top_sources": [
            {"source": r.get("source"), "n": int(r.get("n") or 0)}
            for r in (top_sources or [])
        ],
    }

def score_cluster(arts: List[Dict[str, Any]]) -> float:
    if not arts:
        return 0.0
    u_sources = {a["source"] for a in arts}
    cred = sum(get_source_effective_weight(s) for s in u_sources)
    try:
        dt = _coerce_datetime(arts[0]["created_at"]) or datetime.datetime.now()
        hrs = (datetime.datetime.now() - dt).total_seconds() / 3600
    except Exception as e:
        log.debug(f"Failed to calculate cluster age: {e}")
        hrs = 24
    recency = math.exp(-0.115 * hrs)
    clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    return cred * recency * math.log1p(len(arts)) * (1 + math.log1p(clicks) * 0.15)

def score_cluster_for_synthesis(arts: List[Dict[str, Any]]) -> float:
    if not arts:
        return 0.0
    ranked = rank_articles_in_cluster(arts)
    base = score_cluster(ranked)
    src_bonus = 1 + min(0.8, math.log1p(len({a["source"] for a in ranked})) * 0.28)
    ctx_bonus = 1 + min(
        0.35, sum(1 for a in ranked if str(a.get("description")).strip()) * 0.08
    )
    return base * src_bonus * ctx_bonus

def score_cluster_for_homepage(arts: List[Dict[str, Any]]) -> float:
    if not arts:
        return 0.0
    ranked = rank_articles_in_cluster(arts)
    base = score_cluster(ranked)
    w = [get_source_effective_weight(a["source"]) for a in ranked[:3]]
    t_bonus = 1 + max(0.0, min(0.22, (sum(w) / len(w) - 1.0) * 0.16))
    return base * t_bonus * (0.72 if len({a["source"] for a in ranked}) <= 1 else 1.0)

def assess_cluster_synthesis_freshness(
    arts: List[Dict[str, Any]], synth_at
) -> Dict[str, Any]:
    if not arts:
        return {
            "refresh_needed": False,
            "is_stale": False,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": None,
            "synthesis_updated_at": _coerce_datetime(synth_at),
        }
    ranked = rank_articles_in_cluster(arts)
    s_dt = _coerce_datetime(synth_at)
    latest_article_at = max(
        (_coerce_datetime(a.get("created_at")) for a in ranked), default=None
    )
    if not s_dt:
        return {
            "refresh_needed": True,
            "is_stale": True,
            "reasons": ["missing_synthesis"],
            "new_article_count": len(ranked),
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": None,
        }

    newer = [
        a
        for a in ranked
        if (_coerce_datetime(a.get("created_at")) or datetime.datetime.min) > s_dt
    ]
    older = [a for a in ranked if a not in newer]

    if not newer:
        return {
            "refresh_needed": False,
            "is_stale": False,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": s_dt,
        }

    reasons = []
    score = 0.0
    newer_sources = {a.get("source") for a in newer if a.get("source")}
    older_sources = {a.get("source") for a in older if a.get("source")}
    net_new = [s for s in newer_sources if s not in older_sources]

    if net_new:
        score += min(2.0, 1.0 + len(net_new) * 0.4)
        reasons.append("new_sources")

    def get_nums(articles_list):
        nums = set()
        for a in articles_list:
            nums |= set(
                re.findall(
                    r"\b\d+(?::\d+)?(?:[%.,]\d+)?\b",
                    f"{a.get('title')} {a.get('description')}",
                )
            )
        return nums

    if get_nums(newer) - get_nums(older):
        score += 1.1
        reasons.append("new_numbers")

    if (
        older
        and _cluster_title_overlap(str(newer[0].get("title")), str(older[0].get("title")))
        < 0.26
    ):
        score += 0.9
        reasons.append("new_angle")

    if len(newer) >= 2:
        score += 0.5
        reasons.append("multiple_new_reports")

    if any(get_source_effective_weight(str(a.get("source"))) >= 1.45 for a in newer):
        score += 0.65
        reasons.append("credible_new_reporting")

    current_score = score_cluster_for_synthesis(ranked)
    if current_score >= 3.5:
        score += 0.5
        reasons.append("high_priority_cluster")

    if is_balanced(ranked) and not is_balanced(older):
        score += 1.2
        reasons.append("broad_coverage_achieved")

    age_min = max(
        0.0, ((latest_article_at or s_dt) - s_dt).total_seconds() / 60.0
    )
    min_cooldown = 40 if current_score < 4.0 else 20
    refresh_needed = (score >= 2.0 or len(newer) >= 4) and not (
        age_min < min_cooldown and (len(newer) < 2 and not net_new)
    )

    return {
        "refresh_needed": refresh_needed,
        "is_stale": refresh_needed,
        "freshness_score": round(score, 3),
        "reasons": reasons,
        "new_article_count": len(newer),
        "latest_article_at": latest_article_at,
        "synthesis_updated_at": s_dt,
    }

def is_balanced(arts: List[Dict[str, Any]]) -> bool:
    if len(arts) < BALANCED_COVERAGE_THRESHOLD:
        return False
    reg = get_source_registry()
    return (
        len({a["source"] for a in arts}) >= 4
        or len({reg.get(a["source"], {}).get("category") for a in arts}) >= 2
    )
