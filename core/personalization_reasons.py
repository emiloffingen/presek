"""Explain why a cluster was recommended for a reader profile."""

from __future__ import annotations

from collections import Counter


def _norm_list(values, limit=12) -> list[str]:
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


def _build_why_summary(
    matched_topics: list[str],
    matched_sources: list[str],
    labels: list[str],
    lang: str,
) -> str:
    items = _norm_list([*matched_topics, *matched_sources], limit=3)
    if not items and labels:
        for label in labels:
            if ":" in label:
                items.append(label.split(":", 1)[1].strip())
            if len(items) >= 3:
                break
    if not items:
        return ""
    prefix = "Затоа што следите" if lang == "mk" else "Zato što pratite"
    return f"{prefix}: {', '.join(items)}"


def build_personalization_reasons(
    *,
    profile: dict,
    articles: list[dict],
    metadata: dict | None = None,
    lang: str = "sr",
    similarity: float | None = None,
) -> dict:
    metadata = metadata or {}
    is_mk = lang == "mk"
    followed_topics = {t.casefold(): t for t in _norm_list(profile.get("followedTopics") or [])}
    followed_sources = {s.casefold(): s for s in _norm_list(profile.get("followedSources") or [])}

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

    cluster_topics = _norm_list(
        [a.get("topic") for a in articles if a.get("topic")]
        + [a.get("category") for a in articles if a.get("category")]
    )
    cluster_sources = _norm_list([a.get("source") for a in articles if a.get("source")])
    cluster_tags = _norm_list(metadata.get("tags") if isinstance(metadata.get("tags"), list) else [])

    reasons: list[tuple[float, str]] = []

    for topic in cluster_topics:
        key = topic.casefold()
        if key in followed_topics:
            label = followed_topics[key]
            reasons.append((3.2, f"Следена тема: {label}" if is_mk else f"Praćena tema: {label}"))
        elif topic_counts.get(key, 0) >= 2:
            count = topic_counts[key]
            if is_mk:
                reasons.append(
                    (
                        2.0,
                        (f"Често читате {topic}" if count >= 3 else f"Поврзано со {topic}"),
                    )
                )
            else:
                reasons.append(
                    (
                        2.0,
                        (f"Često čitate {topic}" if count >= 3 else f"Povezano sa {topic}"),
                    )
                )

    for source in cluster_sources:
        key = source.casefold()
        if key in followed_sources:
            label = followed_sources[key]
            reasons.append((2.9, f"Следен извор: {label}" if is_mk else f"Praćeni izvor: {label}"))
        elif source_counts.get(key, 0) >= 2:
            if is_mk:
                reasons.append((1.6, f"{source} често се појавува во вашето читање"))
            else:
                reasons.append((1.6, f"{source} često se pojavljuje u vašem čitanju"))

    for tag in cluster_tags:
        key = tag.casefold()
        if tag_counts.get(key, 0) >= 2:
            reasons.append((1.4, f"Поврзано со {tag}" if is_mk else f"Povezano sa {tag}"))

    if similarity is not None and similarity >= 0.55 and not reasons:
        reasons.append(
            (
                1.1,
                ("Слично на приказните што неодамна ги читавте" if is_mk else "Slično pričama koje ste nedavno čitali"),
            )
        )
    elif similarity is not None and similarity >= 0.7:
        reasons.append(
            (
                0.9,
                ("Семантички блиску до вашите интереси" if is_mk else "Semantički blizu vaših interesovanja"),
            )
        )

    reasons.sort(key=lambda item: item[0], reverse=True)
    labels = [label for _, label in reasons[:3]]

    matched_topics = [
        followed_topics[topic.casefold()] for topic in cluster_topics if topic.casefold() in followed_topics
    ]
    matched_sources = [
        followed_sources[source.casefold()] for source in cluster_sources if source.casefold() in followed_sources
    ]

    top = labels[0] if labels else ("Препорака според вашиот профил" if is_mk else "Preporuka prema vašem profilu")

    return {
        "reason": top,
        "match_reasons": labels,
        "matched_topics": matched_topics[:4],
        "matched_sources": matched_sources[:4],
        "why_summary": _build_why_summary(matched_topics, matched_sources, labels, lang),
    }
