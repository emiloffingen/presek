"""Deterministic clustering fallback for the MK-only deployment."""

import datetime
import re
import uuid
from collections import Counter
from difflib import SequenceMatcher

from core.language import transliterate_cyr_to_lat

MAX_CLUSTER_SIZE = 40
VECTOR_THRESHOLD = 0.28
# Title-overlap merge thresholds. The old single gate (instant 0.92 / best 0.52)
# under-merged badly: semantically identical headlines about one event scored
# 0.27-0.53 and split into separate clusters, which starved pluralism and
# synthesis (91% of clusters ended up single-source). We now merge on two bands:
#   * INSTANT: near-identical headlines.
#   * BEST:    strong combined signal (overlap + shared named entities + topic).
#   * ANCHORED: weaker overlap, but at least one shared named entity (e.g. the
#     same person/place), which is a reliable same-story signal for news.
_TITLE_INSTANT_MERGE = 0.72
_TITLE_BEST_MERGE = 0.40
_TITLE_ANCHORED_MERGE = 0.32
_STOPWORDS = {
    "а",
    "и",
    "во",
    "в",
    "до",
    "за",
    "од",
    "со",
    "на",
    "не",
    "ќе",
    "се",
    "што",
    "кој",
    "која",
    "кои",
    "ова",
    "овој",
    "оваа",
    # Broadcast/format noise: these prefixes appear on unrelated headlines from
    # the same outlets and inflate title overlap (e.g. "(ВИДЕО) ...").
    "видео",
    "фото",
    "фотографии",
    "погледнете",
    "ексклузивно",
    "the",
    "and",
    "for",
    "from",
    "with",
    "this",
    "that",
}


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


def _normalize_entity_token(value) -> str:
    """Casefold, transliterate and strip diacritics so cyr/lat forms compare equal."""
    return (
        transliterate_cyr_to_lat(str(value).casefold())
        .replace("č", "c")
        .replace("ć", "c")
        .replace("š", "s")
        .replace("ž", "z")
    )


# High-frequency, story-agnostic tokens that must never count as a shared "named
# entity" anchor. Headlines about wholly different events constantly share these
# (Европа, Македонија, претседател, влада...), so treating them as anchors chained
# unrelated stories into one cluster. Stored in normalized Latin form (see
# `_normalize_entity_token`). Specific proper nouns (people, clubs, brands) are
# intentionally NOT listed here and remain valid anchors.
_GENERIC_ENTITY_TOKENS = {
    # geography / geopolitics
    "evropa", "evropata", "evropski", "evropska", "evropskiot", "evropskite", "evropskata",
    "makedonija", "makedonijata", "makedonski", "makedonska",
    "srbija", "srbijata", "srpski", "srpska",
    "svet", "svetot", "svetski", "svetska",
    "balkan", "balkanot", "balkanski",
    "region", "regionot", "regionalni",
    "skopje", "beograd", "zagreb", "kosovo", "albanija", "bugarija", "grcija",
    "germanija", "francija", "rusija", "ukraina", "amerika", "sad",
    "britanija", "anglija", "kitajska", "indija", "iran", "izrael", "palestina",
    "njujork", "vasinton", "moskva", "berlin", "pariz", "london",
    # Macedonian cities/regions that appear in a large share of local headlines
    "bitola", "ohrid", "kumanovo", "tetovo", "gostivar", "strumica", "vele",
    "prilep", "stip", "gevgelija", "kavadarci", "struga", "debar", "krusevo",
    # remaining municipalities/regions — a location alone is rarely the story, so
    # treating these as anchors chained unrelated local items into one bag
    "veles", "berovo", "brvenica", "prespa", "delcevo", "kocani", "resen",
    "negotino", "valandovo", "dojran", "pehcevo", "kratovo", "vinica",
    "probistip", "bogdanci", "radovis", "kicevo", "kamenica", "brod",
    "demir hisar", "demir kapija", "sveti nikole", "saraj", "cair", "butel",
    "karpos", "aerodrom", "kisela voda", "gazi baba", "gorce petrov",
    "suto orizari", "zlokukani", "reka", "resan", "prespansko", "ohridsko",
    "eu", "unija", "nato", "oon", "un", "zapad", "istok", "sever", "jug", "evroatlantski",
    # nationality/derived adjective forms (appear in a huge share of world-news headlines)
    "amerikanski", "amerikanska", "amerikanskite", "amerikanec", "amerikanka",
    "ruski", "ruska", "ruskite", "rusite", "rusi", "ruskoto",
    "britanski", "britanska", "britancite", "angliski", "angliska",
    "germanski", "germanska", "francuski", "francuska", "grcki", "grchkata",
    "kitajski", "kitajska", "indiski", "indiska", "iranski", "iranska",
    "evropskoto", "svetskoto", "balkanskite", "makedonskite", "srpskite",
    # institutions / offices / generic actors
    "vlada", "vladata", "vlast", "vlasta", "republika", "republikata", "drzava", "drzavata",
    "pretsedatel", "pretsedatelot", "pretsedatelka", "premier", "premiera", "premijer", "premijerot",
    "minister", "ministerot", "ministerka", "ministerstvoto", "ministerstvata", "ministar",
    "parlament", "parlamentot", "sobranie", "sobranieto", "vladata",
    "opstina", "opstinata", "opstinite", "grad", "gradot", "gradonacelnik", "gradonacelnikot",
    "sud", "sudot", "policija", "policijata", "armija", "vojska", "vojskata",
    "crkva", "crkvata", "kompanija", "banka", "univerzitet", "institut",
    # generic time words capitalised at sentence start
    "godina", "godinava", "godini", "denes", "utre", "vcera", "nedela", "mesec",
    # sentence-initial question/metric words that are not proper nouns
    "zosto", "kako", "koga", "kade", "dali", "kolku", "poveke", "najmalku",
    "pari", "cena", "ceni", "crite", "vesti", "novosti", "video", "foto",
    # parties (appear in a large share of political headlines)
    "vmro", "dpmne", "sdsm", "dui", "levica", "alternativa",
}

# Nationality/geography roots whose inflected forms are all story-agnostic. A
# prefix test avoids enumerating every case/gender/definite ending.
_GENERIC_ENTITY_PREFIXES = (
    "evrop", "makedon", "srb", "balkan", "amerikan", "rusk", "rusit", "rusi",
    "britan", "anglis", "germansk", "francusk", "grchk", "grck", "kitajsk",
    "indisk", "iransk", "izraelsk", "palestin", "njujork", "vasington",
    "mosk", "berlin", "pariz", "london", "zapadnobalk", "evroatlant",
)


def _extract_title_entities(title: str, *args, **kwargs) -> set[str]:
    text = str(title or "")
    entities = set(re.findall(r"\b\d[\d.,]*\b", text))
    for token in re.findall(r"\b[А-ШЃЌЅЉЊЏA-Z][\w-]{2,}\b", text):
        folded = token.casefold()
        if folded in _STOPWORDS:
            continue
        normalized = _normalize_entity_token(token)
        if normalized in _GENERIC_ENTITY_TOKENS:
            continue
        if normalized.startswith(_GENERIC_ENTITY_PREFIXES):
            continue
        entities.add(folded)
    return entities


def _entity_token_overlap(left, right, *args, **kwargs):
    return {_normalize_entity_token(item) for item in (left or set())} & {
        _normalize_entity_token(item) for item in (right or set())
    }


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
    best_anchored = False
    for cluster_id, articles in candidates.items():
        if len(articles) >= MAX_CLUSTER_SIZE:
            continue
        # Star anchor: compare against the cluster's oldest in-window article
        # (the seed) only. Matching against any of the 3 newest members let a
        # heterogeneous bag drift — each new headline only had to resemble one
        # off-topic member to join — so every member must match this single
        # stable seed instead (depth 1, no transitive chaining).
        article = articles[-1]
        other_title = str(article.get("title") or "")
        overlap = _cluster_title_overlap(title, other_title)
        if overlap >= _TITLE_INSTANT_MERGE:
            return cluster_id
        shared = _entity_token_overlap(title_entities, _extract_title_entities(other_title))
        same_topic = bool(topic and article.get("topic") and topic == article["topic"])
        score = overlap
        if shared:
            score += 0.15
        if len(shared) >= 2:
            score += 0.05
        if same_topic:
            score += 0.06
        if source and article.get("source") == source:
            score -= 0.04
        if score > best_score:
            best_id, best_score, best_anchored = cluster_id, score, bool(shared)

    if best_id is None:
        return uuid.uuid4().hex[:12]
    if best_score >= _TITLE_BEST_MERGE:
        return best_id
    # Low band: only merge when the match is anchored by a shared named entity,
    # so unrelated stories that merely share topic words stay separate.
    if best_score >= _TITLE_ANCHORED_MERGE and best_anchored:
        return best_id
    return uuid.uuid4().hex[:12]
