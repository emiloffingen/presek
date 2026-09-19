"""Deterministic clustering fallback for the MK-only deployment."""

import datetime
import re
import uuid
from collections import Counter
from difflib import SequenceMatcher

from core.language import transliterate_cyr_to_lat

MAX_CLUSTER_SIZE = 40
VECTOR_THRESHOLD = 0.28
_STOPWORDS = {"а", "и", "во", "в", "до", "за", "од", "со", "на", "не", "ќе", "се", "што", "кој", "која", "кои", "ова", "овој", "оваа", "the", "and", "for", "from", "with", "this", "that"}


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"[^\w\s-]", " ", str(text or "").casefold())
    return [sr_stem(token) for token in re.findall(r"[\w-]{3,}", normalized) if token not in _STOPWORDS]


def _cluster_title_overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 1.0 if str(left or "").strip().casefold() == str(right or "").strip().casefold() else 0.0
    left_set, right_set = set(left_tokens), set(right_tokens)
    jaccard = len(left_set & right_set) / len(left_set | right_set or {"_"})
    sequence = SequenceMatcher(None, " ".join(left_tokens), " ".join(right_tokens)).ratio()
    return max(jaccard, sequence * 0.85)


def _title_phrase_overlap(left: str, right: str, *args, **kwargs) -> float:
    return _cluster_title_overlap(left, right)


def _extract_title_entities(title: str, *args, **kwargs) -> set[str]:
    text = str(title or "")
    entities = set(re.findall(r"\b\d[\d.,]*\b", text))
    entities.update(
        token.casefold()
        for token in re.findall(r"\b[А-ШЃЌЅЉЊЏA-Z][\w-]{2,}\b", text)
        if token.casefold() not in _STOPWORDS
    )
    return entities


def _entity_token_overlap(left, right, *args, **kwargs):
    def normalize(value):
        return transliterate_cyr_to_lat(str(value).casefold()).replace("č", "c").replace("ć", "c").replace("š", "s").replace("ž", "z")

    return {normalize(item) for item in (left or set())} & {normalize(item) for item in (right or set())}


def _meaningful_entity_token_overlap(left, right, *args, **kwargs) -> float:
    shared = _entity_token_overlap(left, right)
    total = {str(item).casefold() for item in (left or set())} | {str(item).casefold() for item in (right or set())}
    return len(shared) / len(total or {"_"})


def _age_hours(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 999.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - value).total_seconds() / 3600)


def text_to_vector(text: str, *args, **kwargs) -> Counter:
    return Counter(_tokens(text))


def get_cosine(left: Counter, right: Counter) -> float:
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = sum(value * value for value in left.values()) ** 0.5
    right_norm = sum(value * value for value in right.values()) ** 0.5
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def sr_stem(word: str) -> str:
    value = str(word or "")
    if len(value) < 4:
        return value
    for suffix in ("anje", "enje", "ови", "еви", "ите", "ата"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[: -len(suffix)]
    return value


def generate_embeddings_batch(*args, **kwargs):
    return []


def find_or_create_cluster(conn, title, recent_articles, **kwargs):
    """Match a headline to a recent compatible cluster or create a short ID."""
    title = str(title or "").strip()
    if not title:
        return uuid.uuid4().hex[:12]

    category = kwargs.get("category")
    topic = kwargs.get("topic")
    source = kwargs.get("source")
    title_entities = _extract_title_entities(title)
    candidates = {}
    for article in recent_articles or []:
        cluster_id = article.get("cluster_id")
        if not cluster_id or _age_hours(article.get("created_at")) > 24:
            continue
        if article.get("category") and category and article["category"] != category:
            continue
        candidates.setdefault(cluster_id, []).append(article)

    best_id = None
    best_score = 0.0
    for cluster_id, articles in candidates.items():
        if len(articles) >= MAX_CLUSTER_SIZE:
            continue
        for article in articles[:3]:
            other_title = str(article.get("title") or "")
            overlap = _cluster_title_overlap(title, other_title)
            if overlap >= 0.92:
                return cluster_id
            shared = _entity_token_overlap(title_entities, _extract_title_entities(other_title))
            score = overlap + (0.12 if len(shared) >= 2 else 0.05 if shared else 0.0)
            if source and article.get("source") == source:
                score -= 0.04
            if topic and article.get("topic") and topic == article["topic"]:
                score += 0.04
            if score > best_score:
                best_id, best_score = cluster_id, score

    return best_id if best_score >= 0.52 else uuid.uuid4().hex[:12]
