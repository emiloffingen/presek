import datetime
import math
import logging
from config import SOURCE_CATEGORIES

log = logging.getLogger("presek")


def _coerce_datetime(value):
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value
    if not value:
        return None
    try:
        s = str(value).replace(" ", "T")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        try:
            import re

            m = re.match(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", str(value))
            if m:
                return datetime.datetime.fromisoformat(m.group(1).replace(" ", "T"))
            return None
        except (ValueError, TypeError, re.error):
            return None


def _cluster_title_overlap(left: str, right: str) -> float:
    left_terms = {token for token in str(left or "").lower().split() if len(token) >= 4}
    right_terms = {
        token for token in str(right or "").lower().split() if len(token) >= 4
    }
    union = len(left_terms | right_terms) or 1
    return len(left_terms & right_terms) / union


from utils import (
    get_source_effective_weight,
    get_source_trust_label,
    is_balanced,
    get_source_registry,
)


def score_cluster(arts):
    now = datetime.datetime.now()
    unique_sources = {a["source"] for a in arts}
    cred_score = sum(get_source_effective_weight(s) for s in unique_sources)
    try:
        ts = arts[0]["created_at"]
        if isinstance(ts, datetime.datetime):
            latest = ts.replace(tzinfo=None)
        else:
            latest = datetime.datetime.fromisoformat(ts.replace("+00:00", ""))
        hours_old = (now - latest).total_seconds() / 3600
    except Exception:
        hours_old = 24
    recency = math.exp(-0.115 * hours_old)
    breadth = math.log1p(len(arts))
    total_clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    click_bonus = 1 + math.log1p(total_clicks) * 0.15
    return cred_score * recency * breadth * click_bonus


def score_cluster_for_synthesis(arts):
    if not arts:
        return 0.0
    ranked = rank_articles_in_cluster(arts)
    base_score = score_cluster(ranked)
    unique_sources = {a.get("source") for a in ranked if a.get("source")}
    source_count = len(unique_sources)
    source_bonus = 1 + min(0.8, math.log1p(source_count) * 0.28)
    described_articles = sum(
        1 for a in ranked if str(a.get("description") or "").strip()
    )
    context_bonus = 1 + min(0.35, described_articles * 0.08)
    title_terms = []
    for article in ranked[:6]:
        terms = {
            token
            for token in str(article.get("title") or "").lower().split()
            if len(token) >= 4
        }
        if terms:
            title_terms.append(terms)
    disagreement_bonus = 1.0
    if len(title_terms) >= 2:
        overlaps = []
        for idx in range(len(title_terms) - 1):
            left, right = title_terms[idx], title_terms[idx + 1]
            union = len(left | right) or 1
            overlaps.append(len(left & right) / union)
        if overlaps:
            avg_overlap = sum(overlaps) / len(overlaps)
            disagreement_bonus = 1 + max(0.0, min(0.28, (0.55 - avg_overlap) * 0.7))
    return base_score * source_bonus * context_bonus * disagreement_bonus


def score_cluster_for_homepage(arts):
    if not arts:
        return 0.0
    ranked = rank_articles_in_cluster(arts)
    base_score = score_cluster(ranked)
    unique_sources = {a.get("source") for a in ranked if a.get("source")}
    source_count = len(unique_sources)
    signals = build_cluster_source_signals(ranked)
    avg_top_weight = 0.0
    if ranked:
        weights = [
            get_source_effective_weight(str(article.get("source") or ""))
            for article in ranked[:3]
        ]
        avg_top_weight = sum(weights) / len(weights)
    trust_bonus = 1 + max(0.0, min(0.22, (avg_top_weight - 1.0) * 0.16))
    corroborated = sum(1 for signal in signals if signal.get("corroborated_by", 0) >= 1)
    corroboration_bonus = 1 + min(0.24, corroborated * 0.07)
    reg = get_source_registry()
    category_count = len(
        {
            reg.get(str(article.get("source") or ""), {}).get("category", "Локални")
            for article in ranked
            if article.get("source")
        }
    )
    breadth_bonus = (
        1
        + min(0.2, max(0, source_count - 1) * 0.06)
        + min(0.08, max(0, category_count - 1) * 0.04)
    )
    recent_cutoff = datetime.datetime.now() - datetime.timedelta(hours=6)
    recent_developments = sum(
        1
        for article in ranked
        if (_coerce_datetime(article.get("created_at")) or datetime.datetime.min)
        >= recent_cutoff
    )
    development_bonus = 1 + min(0.18, max(0, recent_developments - 1) * 0.06)
    thin_penalty = 1.0
    if source_count <= 1:
        thin_penalty *= 0.72
    elif source_count == 2 and not any(
        signal.get("corroborated_by", 0) >= 1 for signal in signals
    ):
        thin_penalty *= 0.88
    description_count = sum(
        1 for article in ranked if str(article.get("description") or "").strip()
    )
    if description_count <= 1 and source_count <= 2:
        thin_penalty *= 0.9
    return (
        base_score
        * trust_bonus
        * corroboration_bonus
        * breadth_bonus
        * development_bonus
        * thin_penalty
    )


def rank_articles_in_cluster(arts, prefer_recent=False):
    if not arts:
        return []

    def initial_weight(article):
        source_weight = get_source_effective_weight(article["source"])
        description_bonus = (
            0.12 if str(article.get("description") or "").strip() else 0.0
        )
        if prefer_recent:
            created_at = (
                _coerce_datetime(article.get("created_at")) or datetime.datetime.min
            )
            return created_at.timestamp() + (source_weight * 0.001)
        return source_weight + description_bonus

    sorted_arts = sorted(arts, key=initial_weight, reverse=True)
    ranked = []
    seen_norm_titles = []
    for article in sorted_arts:
        title = str(article.get("title") or "").strip()
        is_redundant = any(
            _cluster_title_overlap(title, rep) >= 0.85 for rep in seen_norm_titles
        )
        enriched = dict(article)
        enriched["is_redundant"] = is_redundant
        ranked.append(enriched)
        if not is_redundant:
            seen_norm_titles.append(title)

    def final_sort_key(article):
        redundancy_penalty = -5.0 if article.get("is_redundant") else 0.0
        source_weight = get_source_effective_weight(article["source"])
        created_at = (
            _coerce_datetime(article.get("created_at")) or datetime.datetime.min
        )
        if prefer_recent:
            return (redundancy_penalty, created_at, source_weight)
        return (redundancy_penalty + source_weight, created_at)

    return sorted(ranked, key=final_sort_key, reverse=True)


def build_cluster_source_signals(arts):
    ranked = rank_articles_in_cluster(arts)
    if not ranked:
        return []
    lead = ranked[0]
    lead_title = str(lead.get("title") or "")
    lead_dt = _coerce_datetime(lead.get("created_at"))
    earliest_dt = min(
        (
            _coerce_datetime(a.get("created_at"))
            for a in ranked
            if _coerce_datetime(a.get("created_at"))
        ),
        default=None,
    )
    corroboration_scores = [
        sum(
            1
            for other in ranked
            if other is not article
            and _cluster_title_overlap(
                str(article.get("title") or ""), str(other.get("title") or "")
            )
            >= 0.3
        )
        for article in ranked
    ]
    signals = []
    for index, article in enumerate(ranked):
        source = str(article.get("source") or "")
        title = str(article.get("title") or "")
        effective_weight = get_source_effective_weight(source)
        category = SOURCE_CATEGORIES.get(source, "Локални")
        trust_label = get_source_trust_label(source)
        article_dt = _coerce_datetime(article.get("created_at"))
        overlap_with_lead = (
            1.0 if index == 0 else _cluster_title_overlap(title, lead_title)
        )
        is_earliest = bool(article_dt and earliest_dt and article_dt <= earliest_dt)
        corroborated_by = corroboration_scores[index]
        if index == 0 and corroborated_by >= 2:
            role_label, role_note, role_tone = (
                "Примарен извор",
                "Овој извор ја носи главната линија што ја потврдуваат и повеќе други редакции.",
                "confirm",
            )
        elif index == 0 and effective_weight >= 1.6:
            role_label, role_note, role_tone = (
                "Водечки доверлив извор",
                "Овој извор стои највисоко по доверба и ја дава најцелосната водечка рамка.",
                "lead",
            )
        elif is_earliest and effective_weight >= 1.3:
            role_label, role_note, role_tone = (
                "Прв извештај",
                "Овој извор бил меѓу првите што го објавиле развојот.",
                "lead",
            )
        elif overlap_with_lead < 0.22:
            role_label, role_note, role_tone = (
                "Различен агол",
                "Овој извор ја отвора приказната од друг аспект, а не само ја повторува водечката линија.",
                "contrast",
            )
        elif (
            article_dt
            and lead_dt
            and article_dt > lead_dt + datetime.timedelta(minutes=90)
        ):
            role_label, role_note, role_tone = (
                "Следење / реакција",
                "Овој извор доаѓа подоцна и повеќе носи реакција, последица или follow-up.",
                "context",
            )
        else:
            role_label, role_note, role_tone = (
                "Дополнува контекст",
                "Овој извор ја потврдува главната приказна, но додава и свој контекст или детали.",
                "confirm" if overlap_with_lead >= 0.4 else "context",
            )
        signals.append(
            {
                "role_label": role_label,
                "role_note": role_note,
                "role_tone": role_tone,
                "trust_label": trust_label,
                "source_category": category,
                "effective_weight": round(effective_weight, 3),
                "corroborated_by": corroborated_by,
            }
        )
    return signals


def annotate_cluster_articles(arts, prefer_recent=False):
    ranked = rank_articles_in_cluster(arts, prefer_recent=prefer_recent)
    signals = build_cluster_source_signals(ranked)
    TIER_MAP = {
        "Агенциски": "M",
        "Јавен Сервис": "M",
        "Главни": "M",
        "Независни": "I",
        "Истражувачки": "I",
        "Регионални": "R",
        "Алтернативни": "R",
        "Локални": "R",
    }
    tiers_present = {
        TIER_MAP.get(SOURCE_CATEGORIES.get(art.get("source"), "Локални"), "R")
        for art in ranked
    }
    balance_score = len(tiers_present)
    balance_label = (
        "Широк Консензус"
        if balance_score >= 3
        else ("Разновидни Извори" if balance_score == 2 else None)
    )
    annotated = []
    lead_article = ranked[0] if ranked else None
    for idx, (article, signal) in enumerate(zip(ranked, signals)):
        enriched = dict(article)
        enriched["source_signal"] = signal
        enriched["coverage_balance"] = {"score": balance_score, "label": balance_label}
        if idx == 0:
            enriched["relationship_to_lead"] = {
                "tone": "lead",
                "label": "ОСНОВНА ОБЈАВА",
            }
        else:
            overlap = _cluster_title_overlap(
                lead_article.get("title", ""), article.get("title", "")
            )
            label = (
                "ИСТА ПРИКАЗНА"
                if overlap >= 0.45
                else ("ПОВРЗАНА ПРИКАЗНА" if overlap >= 0.20 else "ИСТ КОНТЕКСТ")
            )
            enriched["relationship_to_lead"] = {"tone": "neutral", "label": label}
        annotated.append(enriched)
    return annotated


def assess_cluster_synthesis_freshness(arts, synthesis_created_at):
    if not arts:
        return {
            "has_synthesis": bool(synthesis_created_at),
            "refresh_needed": False,
            "is_stale": False,
            "freshness_score": 0.0,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": None,
            "synthesis_updated_at": _coerce_datetime(synthesis_created_at),
        }
    ranked = rank_articles_in_cluster(arts)
    synthesis_dt = _coerce_datetime(synthesis_created_at)
    latest_article_at = max(
        (_coerce_datetime(a.get("created_at")) for a in ranked), default=None
    )
    if not synthesis_dt:
        return {
            "has_synthesis": False,
            "refresh_needed": True,
            "is_stale": False,
            "freshness_score": 10.0,
            "reasons": ["missing_synthesis"],
            "new_article_count": len(ranked),
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": None,
        }
    newer, older = [], []
    for article in ranked:
        dt = _coerce_datetime(article.get("created_at"))
        if dt and dt > synthesis_dt:
            newer.append(article)
        else:
            older.append(article)
    if not newer:
        return {
            "has_synthesis": True,
            "refresh_needed": False,
            "is_stale": False,
            "freshness_score": 0.0,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": synthesis_dt,
        }
    score, reasons = 0.0, []
    newer_sources = {a.get("source") for a in newer if a.get("source")}
    older_sources = {a.get("source") for a in older if a.get("source")}
    net_new = [s for s in newer_sources if s not in older_sources]
    if net_new:
        score += min(2.0, 1.0 + len(net_new) * 0.4)
        reasons.append("new_sources")

    def get_nums(arts):
        nums = set()
        for a in arts:
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
        and _cluster_title_overlap(
            str(newer[0].get("title")), str(older[0].get("title"))
        )
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
        0.0, ((latest_article_at or synthesis_dt) - synthesis_dt).total_seconds() / 60.0
    )
    min_cooldown = 40 if current_score < 4.0 else 20
    refresh_needed = (score >= 2.0 or len(newer) >= 4) and not (
        age_min < min_cooldown and (len(newer) < 2 and not net_new)
    )
    return {
        "has_synthesis": True,
        "refresh_needed": refresh_needed,
        "is_stale": refresh_needed,
        "freshness_score": round(score, 3),
        "reasons": reasons,
        "new_article_count": len(newer),
        "latest_article_at": latest_article_at,
        "synthesis_updated_at": synthesis_dt,
    }
