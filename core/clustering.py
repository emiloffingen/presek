"""Deterministic clustering fallback for the MK-only deployment."""

import datetime
import re
import uuid
from collections import Counter
from difflib import SequenceMatcher

from core.embeddings import jina_similarity
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
# Semantic (embedding) recall. Jina-scale cosine >= floor means two headlines are about
# the same event even with little lexical overlap (paraphrase / different outlets).
# Kept conservative: a high-similarity match promotes an otherwise-weak candidate
# over the ANCHORED gate but never bypasses the category guard already applied to
# candidates, and the bonus is capped well below the lexical BEST gate.
_SEMANTIC_SIM_FLOOR = 0.80
_SEMANTIC_SIM_INSTANT = 0.90
_SEMANTIC_BONUS_MAX = 0.22
_SEMANTIC_ANCHOR = 0.86
# Hard semantic gate (Jina scale) against the cluster centroid, applied whenever
# both sides have embeddings. On hand-labelled production stories (Oct 2026,
# tests/fixtures/clustering_regression.json) same-event articles sit at local
# cosine distance <= ~0.55 (95th pct) while different stories about the same
# person (Мицкоски, Ѓорѓиевски, …) start at ~0.58 (5th pct). On a 72h replay
# (scripts/eval_clustering_replay.py) 0.75 left no mixed-story clusters and the
# fewest split duplicates; 0.65 let 21 mixed clusters through.
_SEMANTIC_GATE = 0.75
# Cluster centroid similarity (Jina scale) that overrides a category mismatch,
# and that merges a paraphrase on its own.
_CROSS_CATEGORY_SIM = 0.90
_SEMANTIC_PARAPHRASE = 0.93
# Lexical overlap is checked against this many of the cluster's newest members.
_LEXICAL_MEMBERS = 12
# A cluster stops accepting articles this long after its first article.
MAX_CLUSTER_AGE_HOURS = 36
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
    # Prepositions/conjunctions (len>=3, so _tokens would otherwise keep them
    # and they inflate overlap: "без дозвола", "над 90 милиони"...). They also
    # occur sentence-initially capitalised ("Без струја..."), where the entity
    # extractor would otherwise treat them as named-entity anchors.
    "без",
    "над",
    "под",
    "пред",
    "меѓу",
    "при",
    "кон",
    "низ",
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
    "evropa",
    "evropata",
    "evropski",
    "evropska",
    "evropskiot",
    "evropskite",
    "evropskata",
    "makedonija",
    "makedonijata",
    "makedonski",
    "makedonska",
    "srbija",
    "srbijata",
    "srpski",
    "srpska",
    "svet",
    "svetot",
    "svetski",
    "svetska",
    "balkan",
    "balkanot",
    "balkanski",
    "region",
    "regionot",
    "regionalni",
    "skopje",
    "beograd",
    "zagreb",
    "kosovo",
    "albanija",
    "bugarija",
    "grcija",
    "germanija",
    "francija",
    "rusija",
    "ukraina",
    "amerika",
    "sad",
    "britanija",
    "anglija",
    "kitajska",
    "indija",
    "iran",
    "izrael",
    "palestina",
    "njujork",
    "vasinton",
    "moskva",
    "berlin",
    "pariz",
    "london",
    # Macedonian cities/regions that appear in a large share of local headlines
    "bitola",
    "ohrid",
    "kumanovo",
    "tetovo",
    "gostivar",
    "strumica",
    "vele",
    "prilep",
    "stip",
    "gevgelija",
    "kavadarci",
    "struga",
    "debar",
    "krusevo",
    # remaining municipalities/regions — a location alone is rarely the story, so
    # treating these as anchors chained unrelated local items into one bag
    "veles",
    "berovo",
    "brvenica",
    "prespa",
    "delcevo",
    "kocani",
    "resen",
    "negotino",
    "valandovo",
    "dojran",
    "pehcevo",
    "kratovo",
    "vinica",
    "probistip",
    "bogdanci",
    "radovis",
    "kicevo",
    "kamenica",
    "brod",
    "demir hisar",
    "demir kapija",
    "sveti nikole",
    "saraj",
    "cair",
    "butel",
    "karpos",
    "aerodrom",
    "kisela voda",
    "gazi baba",
    "gorce petrov",
    # single-word components of the multi-word place names above (entity
    # extraction yields single tokens, so "kisela voda" never matched; the two
    # halves anchored unrelated Kisela Voda items into one bag). Common nouns
    # among them (voda=water, baba=grandmother) are never story anchors.
    "kisela",
    "voda",
    "sveti",
    "gazi",
    "baba",
    "suto",
    "orizari",
    # company/product words that behave like the above ("Водовод", "Неделен")
    "vodovod",
    "nedelen",
    "suto orizari",
    "zlokukani",
    "reka",
    "resan",
    "prespansko",
    "ohridsko",
    "eu",
    "unija",
    "nato",
    "oon",
    "un",
    "zapad",
    "istok",
    "sever",
    "jug",
    "evroatlantski",
    # nationality/derived adjective forms (appear in a huge share of world-news headlines)
    "amerikanski",
    "amerikanska",
    "amerikanskite",
    "amerikanec",
    "amerikanka",
    "ruski",
    "ruska",
    "ruskite",
    "rusite",
    "rusi",
    "ruskoto",
    "britanski",
    "britanska",
    "britancite",
    "angliski",
    "angliska",
    "germanski",
    "germanska",
    "francuski",
    "francuska",
    "grcki",
    "grchkata",
    "kitajski",
    "kitajska",
    "indiski",
    "indiska",
    "iranski",
    "iranska",
    "evropskoto",
    "svetskoto",
    "balkanskite",
    "makedonskite",
    "srpskite",
    # institutions / offices / generic actors
    "vlada",
    "vladata",
    "vlast",
    "vlasta",
    "republika",
    "republikata",
    "drzava",
    "drzavata",
    "pretsedatel",
    "pretsedatelot",
    "pretsedatelka",
    "premier",
    "premiera",
    "premijer",
    "premijerot",
    "minister",
    "ministerot",
    "ministerka",
    "ministerstvoto",
    "ministerstvata",
    "ministar",
    "parlament",
    "parlamentot",
    "sobranie",
    "sobranieto",
    "vladata",
    "opstina",
    "opstinata",
    "opstinite",
    "grad",
    "gradot",
    "gradonacelnik",
    "gradonacelnikot",
    "sud",
    "sudot",
    "policija",
    "policijata",
    "armija",
    "vojska",
    "vojskata",
    "crkva",
    "crkvata",
    "kompanija",
    "banka",
    "univerzitet",
    "institut",
    # generic time words capitalised at sentence start
    "godina",
    "godinava",
    "godini",
    "denes",
    "utre",
    "vcera",
    "nedela",
    "mesec",
    # sentence-initial question/metric words that are not proper nouns
    "zosto",
    "kako",
    "koga",
    "kade",
    "dali",
    "kolku",
    "poveke",
    "najmalku",
    "pari",
    "cena",
    "ceni",
    "crite",
    "vesti",
    "novosti",
    "video",
    "foto",
    # sentence-initial adjectives/verbs/nouns that the entity regex picks up
    # (capitalised first word) but that never identify a story: "Тешка
    # сообраќајка...", "Може ли...", "Нема...", "Голема акција...",
    # "Уапсен маж...", "Приведен возач...", "Двајца браќа...", weather
    # ("Променливо облачно..."), "ЦЕЛ БАНКОК...", demographics ("Скопјанка...").
    "teska",
    "teski",
    "tezok",
    "golema",
    "golemi",
    "golem",
    "nova",
    "novi",
    "novo",
    "promenlivo",
    "severna",
    "severen",
    "zapaden",
    "zapadna",
    "dvajca",
    "petmina",
    "nema",
    "moze",
    "ima",
    "uapsen",
    "uapseni",
    "priveden",
    "privedeni",
    "akcija",
    "centar",
    "cel",
    "cela",
    "celo",
    # topic words shared across DIFFERENT stories on the same beat
    "ddv",
    "dizelot",
    "dizel",
    "skopjanka",
    "skopjanec",
    "fon",
    # country/capital names in the same story-agnostic class as the geography
    # entries above (shared by unrelated world-news items)
    "slovenija",
    "turcija",
    "portugalija",
    "kina",
    "kiev",
    "ljubljana",
    "mancester",
    "sofija",
    "atina",
    "podgorica",
    "sarajevo",
    "pristina",
    "tirana",
    # party-acronym forms the existing entries miss ("СДС" != "sdsm",
    # hyphenated "ВМРО-ДПМНЕ" != "vmro"/"dpmne")
    "sds",
    "vmro-dpmne",
    # spelling fix: ќ transliterates to c, so the old "poveke" never matched
    "povece",
    # parties (appear in a large share of political headlines)
    "vmro",
    "dpmne",
    "sdsm",
    "dui",
    "levica",
    "alternativa",
}

# Nationality/geography roots whose inflected forms are all story-agnostic. A
# prefix test avoids enumerating every case/gender/definite ending.
_GENERIC_ENTITY_PREFIXES = (
    "evrop",
    "makedon",
    "srb",
    "balkan",
    "amerikan",
    "rusk",
    "rusit",
    "rusi",
    "britan",
    "anglis",
    "germansk",
    "francusk",
    "grchk",
    "grck",
    "kitajsk",
    "indisk",
    "iransk",
    "izraelsk",
    "palestin",
    "njujork",
    "vasington",
    "mosk",
    "berlin",
    "pariz",
    "london",
    "zapadnobalk",
    "evroatlant",
)


def _extract_title_entities(title: str, *args, **kwargs) -> set[str]:
    text = str(title or "")
    # NOTE: bare numbers ("21", "2025", "500", "4,5") are deliberately NOT
    # entities. They anchored unrelated stories that happened to share a
    # figure ("21-годишен син" vs "21-годишник приведен", "2025" reports vs
    # alcohol stats) via the +0.15 shared-entity bonus.
    entities = set()
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


def _age_hours(value, now=None) -> float:
    if not value:
        return 0.0
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 999.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, (now - value).total_seconds() / 3600)


def text_to_vector(text: str, *args, **kwargs) -> Counter:
    return Counter(_tokens(text))


def get_cosine(left: Counter, right: Counter) -> float:
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = sum(value * value for value in left.values()) ** 0.5
    right_norm = sum(value * value for value in right.values()) ** 0.5
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _parse_vector(value) -> list:
    """Normalize a stored embedding (pgvector string, list, or None) to floats."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        try:
            return [float(x) for x in value]
        except (TypeError, ValueError):
            return []
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        if not s.strip():
            return []
        try:
            return [float(x) for x in s.split(",")]
        except ValueError:
            return []
    return []


def _cosine_of_vectors(a: list, b: list) -> float:
    """Cosine similarity of two already-parsed float vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if not norm_a or not norm_b:
        return 0.0
    return dot / ((norm_a**0.5) * (norm_b**0.5))


def _cosine_similarity(left, right) -> float:
    """Cosine similarity of two embeddings; accepts float lists or pgvector strings."""
    return _cosine_of_vectors(_parse_vector(left), _parse_vector(right))


def sr_stem(word: str) -> str:
    value = str(word or "")
    if len(value) < 4:
        return value
    for suffix in ("anje", "enje", "ови", "еви", "ите", "ата"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[: -len(suffix)]
    return value


def _member_vector(article: dict) -> list:
    """Parsed embedding of a window article, cached on the dict (parsed once per batch)."""
    vec = article.get("_vec")
    if vec is None:
        vec = _parse_vector(article.get("embedding"))
        article["_vec"] = vec
    return vec


def _centroid(vectors: list) -> list:
    dims = len(vectors[0])
    vectors = [v for v in vectors if len(v) == dims]
    return [sum(column) / len(vectors) for column in zip(*vectors)]


def find_or_create_cluster(conn, title, recent_articles, **kwargs):
    """Match a headline to a recent compatible cluster or create a short ID.

    ``recent_articles`` is the newest-first ingestion window. Optional keywords:
    ``embedding``, ``category``, ``topic``, ``source``, ``now`` (the clock, for
    replays; defaults to the current UTC time) and ``cluster_stats``, a mapping
    ``{cluster_id: {"centroid": vector, "started_at": datetime}}`` computed by
    the database. Without ``cluster_stats`` the centroid is averaged from the
    window rows' ``embedding`` and the start time is the earliest
    ``cluster_started_at`` / ``created_at`` among them.

    When the incoming article and the cluster both have embeddings, the
    article must be semantically close to the cluster centroid before any
    lexical signal counts (``_SEMANTIC_GATE``): a shared person or place name
    alone no longer joins two different stories. Without embeddings the
    lexical scoring below is the whole decision.
    """
    title = str(title or "").strip()
    if not title:
        return uuid.uuid4().hex[:12]

    category = kwargs.get("category")
    topic = kwargs.get("topic")
    now = kwargs.get("now")
    cluster_stats = kwargs.get("cluster_stats") or {}
    incoming_vec = _parse_vector(kwargs.get("embedding"))
    title_entities = _extract_title_entities(title)
    candidates = {}
    for article in recent_articles or []:
        cluster_id = article.get("cluster_id")
        if not cluster_id or _age_hours(article.get("created_at"), now) > 24:
            continue
        candidates.setdefault(cluster_id, []).append(article)

    best_id = None
    best_score = 0.0
    best_anchored = False
    best_semantic = 0.0
    for cluster_id, articles in candidates.items():
        if len(articles) >= MAX_CLUSTER_SIZE:
            continue
        # A story stops accepting articles a fixed time after it started, so a
        # long-running cluster cannot drift onto the next day's events.
        stats = cluster_stats.get(cluster_id) or {}
        if stats.get("started_at"):
            cluster_age = _age_hours(stats["started_at"], now)
        else:
            cluster_age = max(_age_hours(a.get("cluster_started_at") or a.get("created_at"), now) for a in articles)
        if cluster_age > MAX_CLUSTER_AGE_HOURS:
            continue

        # Outlets file the same story under different categories (Makedonija vs
        # Amerika for a Haaland lawsuit). A category mismatch is only overruled
        # by a very strong semantic match.
        category_match = not category or any(not a.get("category") or a.get("category") == category for a in articles)

        sim = 0.0
        has_semantic = False
        if incoming_vec:
            centroid = stats.get("centroid") or []
            if isinstance(centroid, str):
                centroid = _parse_vector(centroid)
            if len(centroid) != len(incoming_vec):
                member_vecs = [v for v in (_member_vector(a) for a in articles) if len(v) == len(incoming_vec)]
                centroid = _centroid(member_vecs) if member_vecs else []
            if centroid:
                has_semantic = True
                sim = jina_similarity(_cosine_of_vectors(incoming_vec, centroid))
                if sim < _SEMANTIC_GATE:
                    continue
        if not category_match and not (has_semantic and sim >= _CROSS_CATEGORY_SIM):
            continue

        # Lexical evidence against the best-matching member (newest first), not a
        # single seed: a re-published headline must find its identical twin.
        overlap, other_title = max(
            (_cluster_title_overlap(title, str(a.get("title") or "")), str(a.get("title") or ""))
            for a in articles[:_LEXICAL_MEMBERS]
        )
        shared = _entity_token_overlap(title_entities, _extract_title_entities(other_title))
        same_topic = bool(topic and any(topic == a.get("topic") for a in articles[:_LEXICAL_MEMBERS]))
        if overlap >= _TITLE_INSTANT_MERGE:
            return cluster_id
        # Near-duplicate vectors for the same topic and a shared name are a
        # reliable same-story signal even when the wording was rewritten.
        if sim >= _SEMANTIC_SIM_INSTANT and same_topic and shared:
            return cluster_id
        # A paraphrase this close to the centroid is the same event whatever the
        # wording (no labelled different-story pair comes near it).
        if sim >= _SEMANTIC_PARAPHRASE:
            return cluster_id
        score = overlap
        if shared:
            score += 0.15
        if len(shared) >= 2:
            score += 0.05
        if same_topic:
            score += 0.06
        if has_semantic and sim > _SEMANTIC_SIM_FLOOR:
            score += _SEMANTIC_BONUS_MAX * min((sim - _SEMANTIC_SIM_FLOOR) / (1.0 - _SEMANTIC_SIM_FLOOR), 1.0)
        if score > best_score:
            best_id, best_score, best_anchored, best_semantic = cluster_id, score, bool(shared), sim

    if best_id is None:
        return uuid.uuid4().hex[:12]
    if best_score >= _TITLE_BEST_MERGE:
        return best_id
    # Low band: only merge when the match is anchored by a shared named entity —
    # or by a strong semantic match (paraphrased headline, same event) — so
    # unrelated stories that merely share topic words stay separate.
    if best_score >= _TITLE_ANCHORED_MERGE and (best_anchored or best_semantic >= _SEMANTIC_ANCHOR):
        return best_id
    return uuid.uuid4().hex[:12]
