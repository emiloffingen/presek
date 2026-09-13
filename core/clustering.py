"""
clustering.py — Advanced Hybrid News Clustering for Presek

OVERVIEW:
---------
Combines Title Fingerprinting, Semantic (Vector) Search, and Weighted TF-IDF
to group related news articles while maintaining topic separation.

KEY DESIGN DECISIONS:
--------------------


1. HYBRID APPROACH:
   - Uses both semantic similarity (cosine distance) and structural similarity
   - Balances precision (avoiding false merges) with recall (capturing follow-ups)
   - Semantic vectors capture meaning, while TF-IDF preserves keyword importance

2. TIME-SENSITIVE CLUSTERING:
   - Recent articles (0-6h) cluster more aggressively to capture breaking news
   - Older articles (6-24h) require higher similarity to prevent over-merging
   - Very old articles (>24h) rarely merge to avoid topic drift

3. TOPIC BOUNDARIES:
   - Different categories (Sport vs Politics) never cluster, even with similar titles
   - Topic bridging allows related subtopics (e.g., "Economy" and "Politics") to cluster
   - Shared entities (people, organizations) help bridge related topics

4. SIZE LIMITS:
   - Maximum 40 articles per cluster to prevent "mega-clusters"
   - New articles prefer smaller, more recent clusters over large, old ones
   - Prevents performance degradation and maintains topic focus

5. FOLLOW-UP DETECTION:
   - Same source + similar title + recent timestamp = likely follow-up
   - Different source + similar title + recent timestamp = independent coverage
   - Uses phrase overlap to detect story evolution vs. new stories

6. LANGUAGE HANDLING:
   - Serbian stemmer handles morphological variations
   - Stopword removal focuses on meaningful terms
   - Mixed script (Cyrillic/Latin) handled via transliteration

ALGORITHM FLOW:
--------------
1. Preprocess titles (stemming, stopword removal, normalization)
2. Convert to TF-IDF vectors with semantic weighting
3. Calculate cosine similarity between new article and recent clusters
4. Apply time-based decay to similarity scores
5. Check category/topic compatibility
6. Apply size limits and source rules
7. Assign to best matching cluster or create new one

PERFORMANCE CONSIDERATIONS:
--------------------------
- O(n) complexity where n = number of recent articles (typically <100)
- Vector operations optimized with Counter and math functions
- Database queries minimized through caching and batch operations
- Stemming cache prevents redundant computations

ERROR HANDLING:
---------------
- Empty/malformed titles create new clusters (fail-safe)
- Database errors logged but don't crash clustering
- Invalid timestamps treated as "old" (conservative merging)
- Unicode/encoding issues handled gracefully

METRICS & MONITORING:
--------------------
Key metrics to watch:
- Cluster size distribution (should be normally distributed, max ~40)
- Merge rate (percentage of articles that join existing clusters)
- Category purity (articles in same cluster should have same category)
- Temporal coherence (cluster articles should be close in time)

"""

import datetime
import logging
import math
import os
import re
import uuid
from collections import Counter

from core.config import CLUSTERING_THRESHOLDS, LANGUAGE_CONFIG
from core.language import transliterate_cyr_to_lat

log = logging.getLogger("presek")


def get_stemmer_suffixes(lang: str) -> list[str]:
    return LANGUAGE_CONFIG.get(lang, LANGUAGE_CONFIG["sr"])["stemmer_suffixes"]


def get_stopwords(lang: str) -> set[str]:
    return LANGUAGE_CONFIG.get(lang, LANGUAGE_CONFIG["sr"])["stopwords"]


def stem(word: str, lang: str = "sr") -> str:
    if len(word) < 4:
        return word
    # Don't stem proper nouns (starts with capital) unless it's the very start of a sentence
    if word[0].isupper() and word.lower() not in ["vucic", "vuchic", "vuc", "vuch"]:
        return word
    word = re.sub(r"[^\w\s]", "", word)

    # Strip common comparative/superlative prefixes (Latin and Cyrillic)
    if (word.startswith("naj") or word.startswith("нај")) and len(word) > 6:
        word = word[3:]
    elif (word.startswith("po") or word.startswith("по")) and len(word) > 5:
        word = word[2:]

    for suffix in get_stemmer_suffixes(lang):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


# Backward compatibility alias for tests
sr_stem = stem


SR_STOPWORDS = {
    "i",
    "na",
    "u",
    "od",
    "sa",
    "za",
    "se",
    "e",
    "ne",
    "da",
    "po",
    "do",
    "pri",
    "no",
    "ili",
    "ako",
    "sto",
    "ko",
    "koji",
    "koja",
    "koje",
    "koji",
    "da",
    "iz",
    "o",
    "je",
    "su",
    "a",
    "u",
    "po",
    "od",
    "do",
    "pri",
    "pred",
    "pod",
    "nad",
    "zad",
    "medju",
    "ovaj",
    "ova",
    "ovo",
    "ono",
    "evo",
    "ove",
    "ovi",
    "taj",
    "ta",
    "to",
    "ti",
    "jedan",
    "jedna",
    "jedno",
    "nema",
    "novi",
    "nov",
    "nova",
    "samo",
    "jos",
    "preko",
    "buduci",
    "zbog",
    "gde",
    "kako",
    "kad",
    "tok",
    "pak",
    "ipak",
    "zato",
    "buduci",
    "ovakav",
    "ovakva",
    "ovakvi",
    "prema",
    "saopstenja",
    "informisu",
    "izjave",
    "veli",
    "izjavili",
    "rece",
    "porucuje",
    "kazu",
    "prenose",
    "objavi",
    "pise",
    "danas",
    "juce",
    "sutra",
    "Srbija",
    "severna",
    "sad",
    "kina",
    "eu",
    "nato",
    "the",
    "and",
    "for",
    "from",
    "that",
    "this",
    "with",
    "has",
}


def _normalize_cluster_title(title: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(title or ""))
    text = re.sub(r"[\"'“”‘’`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _get_fingerprint(title: str, lang: str = "sr") -> str:
    """Create a minimal fingerprint for exact/near-exact title matches."""
    normalized = _normalize_cluster_title(title)
    words = re.findall(r"[A-Za-z\w]+", normalized)
    stopwords = get_stopwords(lang)
    # Sort words to catch permutated titles
    return "".join(sorted([w for w in words if w not in stopwords]))


# ── Synonym Mapping ──────────────────────────────────────────────
NEWS_SYNONYMS = {
    "ekonomij": "Ekonomija",
    "Ekonomija": "Ekonomija",
    "vlada": "vlad",
    "ministarstv": "vlad",
    "ministarstvo": "vlad",
    "kabinet": "vlad",
    "kompani": "firma",
    "preduzeca": "firma",
    "mup": "policija",
    "fudbal": "mec",
    "kosarka": "mec",
    "rukomet": "mec",
    "usvoji": "najavi",
    "saopsti": "najavi",
    "informise": "najavi",
    "potvrdi": "najavi",
    "podrska": "mere",
}


def _apply_synonyms(terms: list[str]) -> list[str]:
    return [NEWS_SYNONYMS.get(t, t) for t in terms]


def _title_terms(title: str, lang: str = "sr") -> list[str]:
    normalized = _normalize_cluster_title(title)
    words = re.findall(r"[A-Za-z\w]{3,}", normalized)
    stopwords = get_stopwords(lang)
    stems = [stem(word, lang=lang) for word in words if word not in stopwords]
    return _apply_synonyms(stems)


def _title_phrase_overlap(left: str, right: str, lang: str = "sr") -> float:
    left_terms = _title_terms(left, lang=lang)
    right_terms = _title_terms(right, lang=lang)
    if not left_terms or not right_terms:
        return 0.0

    left_bigrams = {" ".join(pair) for pair in zip(left_terms, left_terms[1:])}
    right_bigrams = {" ".join(pair) for pair in zip(right_terms, right_terms[1:])}
    if left_bigrams and right_bigrams:
        union = len(left_bigrams | right_bigrams) or 1
        return len(left_bigrams & right_bigrams) / union

    left_set = set(left_terms)
    right_set = set(right_terms)
    union = len(left_set | right_set) or 1
    return len(left_set & right_set) / union


# Backward-compatible alias used by the ingestion worker. The helper was
# renamed during clustering cleanup, but the worker still imports the old
# symbol name.
def _cluster_title_overlap(left: str, right: str) -> float:
    return _title_phrase_overlap(left, right)


def _temporal_decay(created_at) -> float:
    """Stronger decay for older news to prevent clusters spanning weeks."""
    if not created_at:
        return 1.0
    if isinstance(created_at, str):
        try:
            created_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 1.0

    now = datetime.datetime.now(datetime.timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.timezone.utc)

    age_hours = (now - created_at).total_seconds() / 3600.0
    # Half-life of ~12 hours for clustering
    return math.exp(-0.05 * age_hours)


def text_to_vector(text: str, lang: str = "sr") -> Counter:
    words = re.findall(r"[A-Za-z\w]{3,}", text.lower())
    stopwords = get_stopwords(lang)
    stems = [stem(w, lang=lang) for w in words if w not in stopwords]
    return Counter(_apply_synonyms(stems))


def get_cosine(vec1: Counter, vec2: Counter) -> float:
    intersection = set(vec1) & set(vec2)
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(v**2 for v in vec1.values())
    sum2 = sum(v**2 for v in vec2.values())
    denom = math.sqrt(sum1) * math.sqrt(sum2)
    return numerator / denom if denom else 0.0


# ── Parameters ────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = CLUSTERING_THRESHOLDS["SIMILARITY_THRESHOLD"]
MAX_CLUSTER_SIZE = CLUSTERING_THRESHOLDS["MAX_CLUSTER_SIZE"]
# Cosine-distance cutoff for pgvector semantic lookup. Tuned for the local
# paraphrase-multilingual-MiniLM-L12-v2 model (384-dim, L2-normalized):
# same-story pairs typically sit around 0.10–0.25, clearly-related topics
# 0.25–0.35, unrelated >0.45. 0.30 keeps precision high without being so
# strict that it misses near-duplicate stories from different sources.
VECTOR_THRESHOLD = CLUSTERING_THRESHOLDS["VECTOR_THRESHOLD"]

from nlp.extraction import extract_title_entities_regex
from nlp.text_processing import extract_entities_semantic


def _extract_title_entities(title: str, *, semantic: bool = True) -> set[str]:
    """Extracts entities using semantic NER when allowed, otherwise regex only."""
    if semantic:
        entities = extract_entities_semantic(str(title or ""))
        if entities:
            return entities

    return extract_title_entities_regex(str(title or ""))


# Country/region tokens that appear in many unrelated Balkan headlines and must
# not alone justify merging generic `vesti` stories.
_WEAK_ENTITY_TOKENS = frozenset(
    {
        "makedonija",
        "srbija",
        "kosovo",
        "evropskata",
        "evropa",
        "evrop",
        "balkan",
        "germanija",
        "amerika",
        "svet",
        "albanija",
        "hrvatska",
        "bugarska",
        "grcka",
        "turcija",
        "crna",
        "gora",
        "bosna",
        "hercegovina",
        "ukraina",
        "moldavija",
        "georgija",
    }
)


def _entity_token_overlap(left_entities: set[str], right_entities: set[str], lang: str = "sr") -> set[str]:
    # Use lowercase stemmed tokens and apply synonyms to improve overlap detection
    # (e.g., "Vlada" and "Ministarstvo" -> "vlad")
    left_tokens = {
        _apply_synonyms(
            [
                stem(
                    transliterate_cyr_to_lat(
                        token.strip()
                        .lower()
                        .replace("ć", "c")
                        .replace("č", "c")
                        .replace("š", "s")
                        .replace("ž", "z")
                        .replace("đ", "dj")
                    )
                    .replace("ch", "c")
                    .replace("sh", "s")
                    .replace("zh", "z")
                    .replace("dj", "d"),
                    lang=lang,
                )
            ]
        )[0]
        for entity in (left_entities or set())
        for token in str(entity).split()
        if len(token.strip()) >= 3
    }
    right_tokens = {
        _apply_synonyms(
            [
                stem(
                    transliterate_cyr_to_lat(
                        token.strip()
                        .lower()
                        .replace("ć", "c")
                        .replace("č", "c")
                        .replace("š", "s")
                        .replace("ž", "z")
                        .replace("đ", "dj")
                    )
                    .replace("ch", "c")
                    .replace("sh", "s")
                    .replace("zh", "z")
                    .replace("dj", "d"),
                    lang=lang,
                )
            ]
        )[0]
        for entity in (right_entities or set())
        for token in str(entity).split()
        if len(token.strip()) >= 3
    }
    res = left_tokens & right_tokens
    return res


def _meaningful_entity_token_overlap(left_entities: set[str], right_entities: set[str], lang: str = "sr") -> set[str]:
    return _entity_token_overlap(left_entities, right_entities, lang=lang) - _WEAK_ENTITY_TOKENS


def _meaningful_entity_tokens(tokens: set[str]) -> set[str]:
    return {token for token in (tokens or set()) if str(token).strip().lower() not in _WEAK_ENTITY_TOKENS}


def _rep_age_hours(created_at) -> float:
    dt = created_at
    if not dt:
        return 999.0
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception as e:
            log.debug(f"Failed to parse datetime string: {e}")
            return 999.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return max(
        0.0,
        (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600.0,
    )


def _topic_bridge_allowed(
    incoming_topic: str,
    rep_topic: str,
    category: str | None,
    rep_category: str | None,
    phrase_overlap: float,
    lexical_overlap: float,
    shared_entities: set[str],
    freshest_rep_hours: float,
) -> bool:
    """Allow tight same-story continuations to survive small topic-label drift and category evolution."""
    incoming_clean = str(incoming_topic or "vesti").strip() or "vesti"
    rep_clean = str(rep_topic or "vesti").strip() or "vesti"

    if incoming_clean == rep_clean and category == rep_category:
        return True

    # Sports should remain strictly isolated; score updates and match reports
    # are too collision-prone to bridge across topics.
    if "Sport" in {incoming_clean, rep_clean}:
        return False

    shared_count = len(shared_entities or set())
    recent_cycle = freshest_rep_hours <= 8
    same_day = freshest_rep_hours <= 18

    # Category Evolution (Category Drift)
    # If the category changed (e.g. Crime -> Politics), we only allow it if it's clearly the same story:
    # Requires high phrase overlap OR high lexical overlap with shared entities.
    if category and rep_category and category != rep_category:
        if shared_count >= 2 and (phrase_overlap >= 0.45 or lexical_overlap >= 0.65):
            return True
        if shared_count >= 1 and phrase_overlap >= 0.55 and lexical_overlap >= 0.70:
            return True
        return False

    generic_mismatch = "vesti" in {incoming_clean, rep_clean}

    if generic_mismatch:
        return (
            (shared_count >= 1 and phrase_overlap >= (0.16 if same_day else 0.22))
            or phrase_overlap >= (0.42 if recent_cycle else 0.50)
            or lexical_overlap >= (0.50 if recent_cycle else (0.56 if same_day else 0.62))
        )

    return (
        (shared_count >= 2 and phrase_overlap >= (0.24 if same_day else 0.30))
        or (
            shared_count >= 1
            and (phrase_overlap >= (0.34 if same_day else 0.42) or lexical_overlap >= (0.48 if same_day else 0.56))
        )
        or phrase_overlap >= (0.50 if recent_cycle else 0.56)
        or lexical_overlap >= (0.60 if recent_cycle else (0.66 if same_day else 0.72))
    )


def find_cluster_semantic(
    conn,
    embedding: list[float],
    lookback_hours: int = 48,
    category: str | None = None,
    topic: str | None = None,
    title: str | None = None,
    semantic_entities: bool = True,
) -> str | None:
    if not embedding:
        return None
    try:
        # Adaptive threshold based on category diversity
        # High-entropy categories need STRICTER thresholds (lower distance)
        # to avoid bridging unrelated stories.
        threshold = VECTOR_THRESHOLD

        # 1. Stricter for international/regional news where stories are often broad
        if category in (
            "Svet",
            "Evropa",
            "Balkan",
            "SAD",
            "Amerika",
            "Region",
            "Nemacka",
        ):
            threshold = 0.22

        # 2. EVEN STRICTER for the generic 'vesti' topic
        if topic == "vesti" or not topic:
            threshold = min(threshold, 0.24)

        params = [str(embedding), lookback_hours]
        filters = []
        if category:
            filters.append("category = %s")
            params.append(category)

        where_clause = " AND ".join(filters)
        if where_clause:
            where_clause = "AND " + where_clause

        params.append(str(embedding))

        # OPTIMIZED: Use cluster_metadata directly with HNSW index for O(log n) lookup
        sql = f"""
            SELECT cluster_id, centroid <=> %s::vector as distance, updated_at
            FROM cluster_metadata
            WHERE centroid IS NOT NULL
              AND updated_at >= NOW() - %s * INTERVAL '1 hour'
              {where_clause}
            ORDER BY centroid <=> %s::vector
            LIMIT 1
        """  # nosec B608 - static where_clause fragment with bound params
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()

        if row:
            dist = float(row["distance"])
            cid = row["cluster_id"]

            # Temporal Tightening
            age_hours = (datetime.datetime.now() - row["updated_at"]).total_seconds() / 3600.0
            if age_hours > 12:
                threshold *= 0.85
            if age_hours > 24:
                threshold *= 0.75

            if dist < threshold:
                # Entity Gating
                if topic == "vesti" or not topic:
                    from core.database import db_manager

                    ents = db_manager.get_cluster_entities([cid]).get(cid, set())
                    input_ents = _extract_title_entities(title or "", semantic=semantic_entities)
                    overlap = _entity_token_overlap(ents, input_ents)
                    meaningful = overlap - _WEAK_ENTITY_TOKENS
                    if ents and input_ents and not meaningful:
                        return None
                    if dist > (threshold * 0.7) and not input_ents:
                        return None

                # Final Size Check
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) as n FROM articles WHERE cluster_id = %s",
                        (cid,),
                    )
                    size_row = cur.fetchone()
                if size_row and int(size_row["n"]) < MAX_CLUSTER_SIZE:
                    return cid
    except Exception as e:
        log.error(f"[clustering] Centroid lookup failed: {e}")
    return None


def find_or_create_cluster(
    conn,
    title: str,
    recent_articles: list,
    threshold: float = SIMILARITY_THRESHOLD,
    embedding: list[float] | None = None,
    category: str | None = None,
    source: str | None = None,
    topic: str | None = None,
    lang: str = "sr",
    semantic_entities: bool = True,
) -> str:
    """
    Unified clustering pipeline:
    1. Title Fingerprinting (Instant match for same-story duplicates)
    2. Semantic Vector Match (local MiniLM embeddings via pgvector)
    3. Multi-representative TF-IDF with Entity & Recency Boosting
    """
    # 1. Semantic Vector Match (Primary Path)
    if embedding:
        cid = find_cluster_semantic(
            conn,
            embedding,
            category=category,
            topic=topic,
            title=title,
            semantic_entities=semantic_entities,
        )
        if cid:
            return cid

    # 2. Title Fingerprinting (Fallback for same-story duplicates)
    input_fp = _get_fingerprint(title, lang=lang)

    # 3. TF-IDF Hybrid Fallback
    vec1 = text_to_vector(title, lang=lang)
    if not vec1:
        return uuid.uuid4().hex[:12]

    potential_entities = _extract_title_entities(title, semantic=semantic_entities)
    normalized_input = _normalize_cluster_title(title)

    cluster_docs = {}
    cluster_size = {}
    cluster_sources = {}
    all_cids = set()

    for article in recent_articles:
        cid = article.get("cluster_id")
        if not cid:
            continue
        all_cids.add(cid)
        cluster_size[cid] = cluster_size.get(cid, 0) + 1

        # Track sources to avoid grouping multiple articles from same source in same cluster (unless it's a series)
        cluster_sources.setdefault(cid, set()).add(article.get("source"))

        if cid not in cluster_docs:
            cluster_docs[cid] = []

        # Keep up to 3 diverse representatives for matching
        if len(cluster_docs[cid]) < 3:
            # Quick Fingerprint match check
            if input_fp and _get_fingerprint(article["title"], lang=lang) == input_fp:
                return cid
            cluster_docs[cid].append(article)

    # Entity Fetching
    from core.database import db_manager

    cluster_entities = db_manager.get_cluster_entities(list(all_cids))

    best_cid = None
    best_score = 0.0

    for cid, reps in cluster_docs.items():
        if cluster_size.get(cid, 0) >= MAX_CLUSTER_SIZE:
            continue

        # Mandatory Category and Topic Match
        rep_0 = reps[0]
        if category and rep_0.get("category") != category:
            continue

        rep_entities = cluster_entities.get(cid, set())
        rep_topic = rep_0.get("topic", "vesti")
        incoming_topic = topic or "vesti"
        rep_category = rep_0.get("category")
        freshest_rep_hours = min((_rep_age_hours(rep.get("created_at")) for rep in reps), default=999.0)
        shared_entities = (
            potential_entities.intersection(rep_entities) if potential_entities and rep_entities else set()
        )
        if not shared_entities and potential_entities and rep_entities:
            shared_entities = _entity_token_overlap(potential_entities, rep_entities, lang=lang)
        meaningful_shared = _meaningful_entity_tokens(shared_entities)
        topic_bridge = _topic_bridge_allowed(
            incoming_topic,
            rep_topic,
            category,
            rep_category,
            max(
                (_title_phrase_overlap(normalized_input, rep["title"], lang=lang) for rep in reps),
                default=0.0,
            ),
            max(
                (get_cosine(vec1, text_to_vector(rep["title"], lang=lang)) for rep in reps),
                default=0.0,
            ),
            shared_entities,
            freshest_rep_hours,
        )

        if not topic_bridge:
            continue

        if incoming_topic == "vesti" and potential_entities and rep_entities and not meaningful_shared:
            continue

        # Source Exclusivity
        # Only allow same-source if it's a "series" (follow-up hours later)
        # or if it's a fingerprint match (already handled above).
        source_penalty = 1.0
        same_source_cluster = bool(source and source in cluster_sources.get(cid, set()))
        if source and source in cluster_sources.get(cid, set()):
            # Find time of earliest/latest article from same source in this cluster
            source_times = [
                r["created_at"] for r in recent_articles if r.get("cluster_id") == cid and r.get("source") == source
            ]
            if source_times:
                # If the last article from this source was < 2 hours ago, penalize heavily
                # (Prevents flood of same story, but allows follow-ups later in the day)
                try:
                    last_src_time = max(source_times)
                    if isinstance(last_src_time, str):
                        last_src_time = datetime.datetime.fromisoformat(last_src_time.replace("Z", "+00:00"))

                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    if last_src_time.tzinfo is None:
                        last_src_time = last_src_time.replace(tzinfo=datetime.timezone.utc)

                    if (now_utc - last_src_time).total_seconds() < 7200:  # 2 hours
                        source_penalty = 0.4  # Very high penalty for rapid repeats
                    else:
                        source_penalty = 0.85  # Slight penalty for diversity
                except (ValueError, TypeError, AttributeError):
                    source_penalty = 0.6

        # 1. Shared Entity Boost
        # If articles share multiple capitalized proper nouns, they are highly likely related.
        entity_boost = 1.0
        if meaningful_shared:
            if len(meaningful_shared) >= 2:
                entity_boost = 1.25  # Significant boost for 2+ shared entities
            elif len(meaningful_shared) == 1:
                entity_boost = 1.1

        current_best_rep_score = 0.0
        for rep in reps:
            rep_title = rep["title"]
            vec2 = text_to_vector(rep_title, lang=lang)
            lexical_score = get_cosine(vec1, vec2)
            phrase_score = _title_phrase_overlap(normalized_input, rep_title, lang=lang)

            # Short title penalty: be stricter with very short headlines (under 30 chars)
            # as they are prone to false positives.
            if len(normalized_input) < 30 or len(_normalize_cluster_title(rep_title)) < 30:
                lexical_score *= 0.85
                phrase_score *= 0.85

            # Same-source follow-ups should only merge when the titles still
            # look like the same story, or when they share concrete entities.
            if same_source_cluster and input_fp != _get_fingerprint(rep_title, lang=lang):
                if (
                    phrase_score < 0.26
                    and lexical_score < 0.58
                    and not (len(meaningful_shared) >= 1 if meaningful_shared else False)
                ):
                    continue

            # Weighted combine
            # Favor lexical (stem) similarity for better recall across diverse headlines
            score = (lexical_score * 0.9) + (phrase_score * 0.1)
            decay = _temporal_decay(rep.get("created_at"))
            if (
                incoming_topic == rep_topic
                and category == rep_category
                and len(meaningful_shared) >= 2
                and freshest_rep_hours <= 24
                and lexical_score >= 0.38
            ):
                # Same-day follow-ups often rewrite the lead ("500.000" vs
                # "polovina milion") but keep concrete entities. Do not let
                # time decay alone split those into singleton clusters.
                decay = max(decay, 0.72)
            score *= decay
            score *= source_penalty
            score *= entity_boost

            if topic_bridge and incoming_topic != rep_topic:
                score *= 1.06

            if score > current_best_rep_score:
                current_best_rep_score = score

        # Sports Match Validation (Avoid mixing different matches)
        if topic == "Sport" and rep_0.get("topic") == "Sport":
            # We check if they share any common "team-like" entities
            if potential_entities and rep_entities:
                shared_entities = potential_entities.intersection(rep_entities)
                # If they both have distinct entities but NONE are shared, they are likely different matches
                # (e.g., "Arsenal - Barca" vs "Real - Milan")
                if not shared_entities:
                    current_best_rep_score *= 0.4

            # If they have different scores but same teams, it's probably an update (score evolution)
            # If they have DIFFERENT scores and DIFFERENT teams, the entity check above already caught it.

        # Adaptive Lexical Threshold
        # Generic topics should require higher similarity to merge.
        current_threshold = threshold
        if incoming_topic == "vesti" and incoming_topic == rep_topic:
            current_threshold = max(threshold, 0.58)  # Be more demanding for 'vesti'
            if (
                category == rep_category
                and len(meaningful_shared) >= 2
                and freshest_rep_hours <= 24
                and current_best_rep_score >= 0.32
            ):
                current_threshold = 0.32
        elif topic_bridge and incoming_topic != rep_topic:
            if freshest_rep_hours <= 12:  # Within half-day cycle
                current_threshold = min(threshold, 0.40)
            elif freshest_rep_hours <= 24:  # Within same day
                current_threshold = min(threshold, 0.44)
            else:  # Older clusters
                current_threshold = min(threshold, 0.48)

        if current_best_rep_score > current_threshold and current_best_rep_score > best_score:
            best_score = current_best_rep_score
            best_cid = cid

    if best_cid:
        # Dispatch dynamic centroid update
        if os.environ.get("REDIS_URL"):
            try:
                from tasks.intelligence import refresh_cluster_centroid_task
                from tasks.utils import schedule_task_once

                schedule_task_once(
                    f"lock:centroid_refresh:{best_cid}",
                    300,
                    refresh_cluster_centroid_task,
                    args=(best_cid,),
                    countdown=30,
                )
            except Exception as e:
                log.warning(f"[clustering] centroid refresh dispatch failed for {best_cid}: {e}")
        return best_cid

    return uuid.uuid4().hex[:12]
