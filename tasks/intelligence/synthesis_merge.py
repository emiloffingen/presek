"""Cluster merge confidence scoring for repair/split operations."""

from __future__ import annotations

import logging

from core.embeddings import average_embeddings, jina_similarity, parse_embedding_value

log = logging.getLogger("presek")


def _compute_centroid_from_values(values):
    return average_embeddings(values)


def _cosine_dist(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0


_GENERIC_CLUSTER_TOPICS = {"vesti", "news", ""}


def _cluster_text_similarity(left_titles, right_titles, lang="mk"):
    import core.clustering as clustering

    left_text = " ".join(str(title or "") for title in (left_titles or [])[:3])
    right_text = " ".join(str(title or "") for title in (right_titles or [])[:3])
    lexical = clustering.get_cosine(
        clustering.text_to_vector(left_text, lang=lang),
        clustering.text_to_vector(right_text, lang=lang),
    )
    phrase = 0.0
    for left in (left_titles or [])[:3]:
        for right in (right_titles or [])[:3]:
            phrase = max(phrase, clustering._title_phrase_overlap(str(left or ""), str(right or ""), lang=lang))
    return lexical, phrase


def _cluster_tag_set(row):
    return {str(tag or "").strip().lower() for tag in (row.get("tags") or []) if str(tag or "").strip()}


def _split_cluster_merge_score(left, right, lang="mk"):
    """Return a merge confidence for two already-created clusters, or 0 if unsafe."""
    if left.get("cluster_id") == right.get("cluster_id"):
        return 0.0
    if left.get("country") != right.get("country"):
        return 0.0
    if left.get("category") and right.get("category") and left.get("category") != right.get("category"):
        return 0.0

    left_topic = str(left.get("topic") or "").strip()
    right_topic = str(right.get("topic") or "").strip()
    if left_topic != right_topic:
        return 0.0

    left_latest = left.get("latest_article")
    right_latest = right.get("latest_article")
    if left_latest and right_latest:
        try:
            if abs((left_latest - right_latest).total_seconds()) > 36 * 3600:
                return 0.0
        except Exception:
            log.debug("Synthesis merge fallback")

    lexical, phrase = _cluster_text_similarity(left.get("titles"), right.get("titles"), lang=lang)
    shared_tags = _cluster_tag_set(left) & _cluster_tag_set(right)
    meaningful_shared_tags = {tag for tag in shared_tags if tag not in _GENERIC_CLUSTER_TOPICS}

    left_centroid = parse_embedding_value(left.get("centroid"))
    right_centroid = parse_embedding_value(right.get("centroid"))
    centroid_similarity = 0.0
    if left_centroid and right_centroid:
        centroid_similarity = jina_similarity(1 - _cosine_dist(left_centroid, right_centroid))

    generic_topic = left_topic.lower() in _GENERIC_CLUSTER_TOPICS
    if generic_topic:
        if len(meaningful_shared_tags) >= 2 and lexical >= 0.30:
            return round(lexical + phrase + len(meaningful_shared_tags) * 0.08 + centroid_similarity * 0.2, 4)
        if len(meaningful_shared_tags) >= 1 and lexical >= 0.24 and centroid_similarity >= 0.78:
            return round(lexical + phrase + centroid_similarity * 0.35, 4)
        return 0.0

    if lexical >= 0.36 or (phrase >= 0.22 and meaningful_shared_tags):
        return round(lexical + phrase + len(meaningful_shared_tags) * 0.06 + centroid_similarity * 0.15, 4)
    return 0.0
