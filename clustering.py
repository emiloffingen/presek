"""
clustering.py — TF-IDF cosine similarity clustering for Пресек
Includes a simple Macedonian suffix stemmer to improve cluster matching.
e.g. "влада" and "владата" now cluster together.

Fixes applied:
  - Threshold raised from 0.15 → 0.35 to prevent false matches
  - Cluster size cap (MAX_CLUSTER) prevents snowball mega-clusters
  - Compares against recent cluster *representatives* (first article per cluster),
    not every article — prevents one big cluster matching everything
"""
import math, uuid, re
import datetime
from collections import Counter
from database import get_db

# ── Macedonian stemmer ────────────────────────────────────────────
MK_SUFFIXES = [
    "увањето", "ување", "ањето", "ање", "ењето", "ење",
    "истите", "истот", "иста", "исти", "ските", "скиот", "ската", "ски", "ска", "ско",
    "ните", "ниот", "ната", "ното", "ни", "ите", "иот", "ата", "ото", "от", "та", "то",
    "вме", "вте", "аа", "еа", "ја", "ше", "ме", "те", "ат", "ет"
]

def mk_stem(word: str) -> str:
    if len(word) < 4: return word
    # Remove punctuation attached to words
    word = re.sub(r'[^\w\s]', '', word)
    for suffix in MK_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word

MK_STOPWORDS = {
    "и","на","во","од","со","за","се","е","не","да","по","до","при",
    "но","или","ако","што","кој","која","кое","кои","дека","оти",
    "ги","го","им","му","ја","ми","ме","те","ве","ни","си","ке",
    "во","со","на","од","до","при","пред","под","над","зад","меѓу",
    "овој","оваа","ова","овие","тој","таа","тоа","тие",
    "еден","една","едно","еднa","нема","нема","нови","нов","нова",
    "само","уште","преку","бидејќи","поради","каде","како","кога",
    "the","and","for","from","that","this","with","has",
}


def _normalize_cluster_title(title: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(title or ""))
    text = re.sub(r"[\"'“”‘’`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _title_terms(title: str) -> list[str]:
    normalized = _normalize_cluster_title(title)
    words = re.findall(r"[а-шА-ШA-Za-z\w]{3,}", normalized)
    return [mk_stem(word) for word in words if word not in MK_STOPWORDS]


def _title_phrase_overlap(left: str, right: str) -> float:
    left_terms = _title_terms(left)
    right_terms = _title_terms(right)
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


def _recency_multiplier(created_at) -> float:
    if not created_at:
        return 1.0
    if isinstance(created_at, str):
        try:
            created_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            return 1.0
    if not isinstance(created_at, datetime.datetime):
        return 1.0
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    age_hours = max(0.0, (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - created_at).total_seconds() / 3600.0)
    if age_hours <= 6:
        return 1.08
    if age_hours <= 24:
        return 1.0
    if age_hours <= 36:
        return 0.92
    return 0.82

def text_to_vector(text: str) -> Counter:
    # Handle both title and description if available
    words = re.findall(r'[а-шА-Ш\w]{3,}', text.lower())
    stems = [mk_stem(w) for w in words if w not in MK_STOPWORDS]
    return Counter(stems)

def get_cosine(vec1: Counter, vec2: Counter) -> float:
    intersection = set(vec1) & set(vec2)
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(v**2 for v in vec1.values())
    sum2 = sum(v**2 for v in vec2.values())
    denom = math.sqrt(sum1) * math.sqrt(sum2)
    return numerator / denom if denom else 0.0

# ── Parameters ────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.55  # Slightly more permissive TF-IDF fallback
MAX_CLUSTER_SIZE     = 30
VECTOR_THRESHOLD     = 0.28  # More permissive semantic matching (0.12 was too strict)

def find_cluster_semantic(embedding: list[float], lookback_hours: int = 36, category: str | None = None) -> str | None:
    """
    Find the closest existing cluster using vector similarity in PostgreSQL.
    Increased lookback to 36h for developing stories.
    """
    if not embedding:
        return None
        
    conn = get_db()
    try:
        # Optimization: use pre-calculated distance limit
        params = [str(embedding), lookback_hours, str(embedding)]
        cat_filter = ""
        if category:
            cat_filter = "AND category = %s"
            params.insert(1, category)

        sql = f"""
            SELECT cluster_id, embedding <=> %s::vector as distance
            FROM articles
            WHERE embedding IS NOT NULL
              {cat_filter}
              AND created_at >= NOW() - %s * INTERVAL '1 hour'
            ORDER BY embedding <=> %s::vector
            LIMIT 1
        """
        row = conn.execute(sql, tuple(params)).fetchone()
        
        if row and float(row['distance']) < VECTOR_THRESHOLD:
            cid = row['cluster_id']
            # Verify cluster is not full
            count = conn.execute("SELECT COUNT(*) FROM articles WHERE cluster_id = %s", (cid,)).fetchone()[0]
            if count < MAX_CLUSTER_SIZE:
                return cid
    except Exception as e:
        import logging
        logging.getLogger("presek").error(f"[clustering] Semantic lookup failed: {e}")
    finally:
        conn.close()
    return None

def find_or_create_cluster(title: str, recent_articles: list, 
                            threshold: float = SIMILARITY_THRESHOLD,
                            embedding: list[float] | None = None,
                            category: str | None = None) -> str:
    """
    Hybrid clustering: 
    1. Try semantic (vector) match if embedding is provided.
    2. Fall back to multi-representative TF-IDF matching with entity boosting.
    3. Create a new UUID if no match.
    """
    # 1. Try Semantic Match
    if embedding:
        cid = find_cluster_semantic(embedding, category=category)
        if cid:
            return cid

    # 2. TF-IDF Fallback
    vec1 = text_to_vector(title)
    if not vec1:
        return str(uuid.uuid4())[:8]

    # Heuristic: extract potential entities from title (capitalized words)
    # This helps in boosting matches even if lexical similarity is low
    potential_entities = set(re.findall(r'[А-Ш][а-ш]+', title))
    normalized_input = _normalize_cluster_title(title)

    cluster_docs: dict[str, list[dict]] = {}
    cluster_size: dict[str, int] = {}
    cluster_cat: dict[str, str] = {}
    all_cids = set()
    
    for article in recent_articles:
        cid = article.get("cluster_id")
        if not cid: continue
        all_cids.add(cid)
        cluster_size[cid] = cluster_size.get(cid, 0) + 1
        if cid not in cluster_docs:
            cluster_docs[cid] = [{"title": article["title"], "created_at": article.get("created_at")}]
            cluster_cat[cid] = article.get("category")
        elif len(cluster_docs[cid]) < 3:
            cluster_docs[cid].append({"title": article["title"], "created_at": article.get("created_at")})

    # Fetch entities for these clusters to enable boosting
    from database import db_manager
    cluster_entities = db_manager.get_cluster_entities(list(all_cids))

    best_cid = None
    best_score = 0.0

    for cid, reps in cluster_docs.items():
        if cluster_size.get(cid, 0) >= MAX_CLUSTER_SIZE:
            continue
        
        # Category hard-filter
        if category and cluster_cat.get(cid) and category != cluster_cat[cid]:
            if category != 'Македонија' and cluster_cat[cid] != 'Македонија':
                continue

        # Check all representatives
        current_best_rep_score = 0.0
        for rep in reps:
            rep_title = rep["title"]
            vec2 = text_to_vector(rep_title)
            lexical_score = get_cosine(vec1, vec2)
            phrase_score = _title_phrase_overlap(normalized_input, rep_title)
            score = lexical_score + min(0.22, phrase_score * 0.35)
            score *= _recency_multiplier(rep.get("created_at"))
            if score > current_best_rep_score:
                current_best_rep_score = score
        
        # Entity Boosting: if they share entities, boost the score
        if cid in cluster_entities and potential_entities:
            shared = potential_entities.intersection(cluster_entities[cid])
            if shared:
                # Boost score by 0.1 for each shared entity, max 0.3
                boost = min(0.3, len(shared) * 0.15)
                current_best_rep_score += boost

        if current_best_rep_score > threshold and current_best_rep_score > best_score:
            best_score = current_best_rep_score
            best_cid = cid

    return best_cid if best_cid else str(uuid.uuid4())[:8]
