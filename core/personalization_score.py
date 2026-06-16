"""Server-side reader profile scoring for personalized news ranking."""

from __future__ import annotations

from collections import Counter

_WEAK_TOPICS = frozenset(
    {
        "vesti",
        "srbija",
        "svet",
        "balkan",
        "sport",
        "kultura",
        "tehnologija",
        "zivot",
        "македонија",
        "свет",
        "спорт",
        "култура",
    }
)


def _norm_list(values, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values or []:
        val = str(raw or "").strip()
        key = val.casefold()
        if not val or key in seen:
            continue
        seen.add(key)
        out.append(val)
        if len(out) >= limit:
            break
    return out


def _is_strong_topic_signal(value: str) -> bool:
    return str(value or "").strip().casefold() not in _WEAK_TOPICS


def _build_reader_signals(profile: dict) -> tuple[Counter[str], Counter[str], Counter[str]]:
    topic_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()

    for recent in profile.get("recentClusters") or []:
        if not isinstance(recent, dict):
            continue
        for topic in _norm_list([recent.get("topic"), recent.get("category")]):
            topic_counts[topic.casefold()] += 1
        for source in _norm_list([*(recent.get("sources") or []), recent.get("primarySource")]):
            source_counts[source.casefold()] += 1
        for tag in _norm_list(recent.get("tags") or []):
            tag_counts[tag.casefold()] += 1

    return topic_counts, source_counts, tag_counts


def score_cluster_for_profile(
    *,
    profile: dict,
    articles: list[dict],
    metadata: dict | None = None,
    lang: str = "sr",
    is_breaking: bool = False,
    cluster_id: str | None = None,
) -> dict:
    """Mirror client-side scoreClusterForReader weights."""
    metadata = metadata or {}
    if not articles:
        return {"profile_score": 0.0, "seen": False, "reasons": []}

    main = articles[0] or {}
    cluster_id = str(cluster_id or main.get("cluster_id") or "").strip()
    sources = _norm_list([a.get("source") for a in articles if a.get("source")])
    cluster_topics = _norm_list(
        [a.get("topic") for a in articles if a.get("topic")]
        + [a.get("category") for a in articles if a.get("category")]
    )
    cluster_tags = _norm_list(metadata.get("tags") if isinstance(metadata.get("tags"), list) else [])

    followed_topics = {t.casefold(): t for t in _norm_list(profile.get("followedTopics") or [])}
    followed_sources = {s.casefold(): s for s in _norm_list(profile.get("followedSources") or [])}
    seen_cluster_ids = {
        str(item.get("cluster_id"))
        for item in (profile.get("recentClusters") or [])
        if isinstance(item, dict) and item.get("cluster_id")
    }

    topic_counts, source_counts, tag_counts = _build_reader_signals(profile)
    score = 0.0
    reasons: list[tuple[float, str]] = []
    is_mk = lang == "mk"

    for topic in cluster_topics:
        key = topic.casefold()
        if key in followed_topics:
            score += 3.2
            label = followed_topics[key]
            reasons.append(
                (3.2, f"Следена тема: {label}" if is_mk else f"Praćena tema: {label}")
            )
        elif _is_strong_topic_signal(topic) and topic_counts.get(key, 0):
            weight = min(2.7, 0.55 + topic_counts[key] * 0.5)
            score += weight
            reasons.append(
                (
                    weight,
                    f"Често читате {topic}" if is_mk else f"Često čitate {topic}",
                )
            )

    for source in sources:
        key = source.casefold()
        if key in followed_sources:
            score += 2.9
            label = followed_sources[key]
            reasons.append(
                (2.9, f"Следен извор: {label}" if is_mk else f"Praćeni izvor: {label}")
            )
        elif source_counts.get(key, 0):
            weight = min(1.65, 0.3 + source_counts[key] * 0.28)
            score += weight
            reasons.append(
                (
                    weight,
                    f"{source} често се појавува во вашето читање"
                    if is_mk
                    else f"{source} često se pojavljuje u vašem čitanju",
                )
            )

    for tag in cluster_tags:
        key = tag.casefold()
        if tag_counts.get(key, 0):
            weight = min(1.9, 0.4 + tag_counts[key] * 0.4)
            score += weight
            reasons.append(
                (weight, f"Поврзано со {tag}" if is_mk else f"Povezano sa {tag}")
            )

    if is_breaking:
        score += 0.65

    score += min(0.9, max(0, len(articles) - 1) * 0.12)

    seen = bool(cluster_id and cluster_id in seen_cluster_ids)
    if seen:
        score -= 1.2

    reasons.sort(key=lambda item: item[0], reverse=True)
    return {
        "profile_score": round(score, 3),
        "seen": seen,
        "reasons": [label for _, label in reasons[:3]],
    }


def blend_personalization_score(
    *,
    similarity: float,
    profile_score: float,
    semantic_weight: float | None = None,
) -> float:
    """Blend semantic similarity with explicit profile signals."""
    import os

    weight = semantic_weight
    if weight is None:
        weight = float(os.environ.get("PERSONALIZATION_BLEND_SEMANTIC", "0.7"))
    weight = max(0.0, min(1.0, float(weight)))
    normalized_profile = max(0.0, min(1.0, float(profile_score) / 6.0))
    return round(weight * float(similarity) + (1.0 - weight) * normalized_profile, 4)
