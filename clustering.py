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
# ... (keep existing stemmer and stopwords) ...
MK_SUFFIXES = [
    "увањето", "ување", "ањето", "ање", "ењето", "ење",
    "истите", "истот", "иста", "исти", "ските", "скиот", "ската", "ски", "ска", "ско",
    "ните", "ниот", "ната", "ното", "ни", "ите", "иот", "ата", "ото", "от", "та", "то",
]

def mk_stem(word: str) -> str:
    if len(word) < 5: return word
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
    "the","and","for","from","that","this","with","has",
}

def text_to_vector(text: str) -> Counter:
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
# Extreme thresholds for "Identical News" only
SIMILARITY_THRESHOLD = 0.75  # TF-IDF must be extremely high
MAX_CLUSTER_SIZE     = 20
VECTOR_THRESHOLD     = 0.08  # Vector distance must be tiny (lower is stricter)

def find_cluster_semantic(embedding: list[float], lookback_hours: int = 24, category: str | None = None) -> str | None:
    """
    Find the closest existing cluster using vector similarity in PostgreSQL.
    Returns cluster_id if a match is found within VECTOR_THRESHOLD.
    If category is provided, it only looks for matches in the same category.
    """
    if not embedding:
        return None
        
    conn = get_db()
    try:
        # We look for the most similar article in the last X hours
        # using the cosine distance operator <=>
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
            # Verify cluster is not full
            cid = row['cluster_id']
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
    2. Fall back to TF-IDF matching against recent articles.
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

    cluster_rep: dict[str, str] = {}
    cluster_size: dict[str, int] = {}
    cluster_cat: dict[str, str] = {}
    
    for article in recent_articles:
        cid = article.get("cluster_id")
        if not cid: continue
        cluster_size[cid] = cluster_size.get(cid, 0) + 1
        if cid not in cluster_rep:
            cluster_rep[cid] = article["title"]
            cluster_cat[cid] = article.get("category")

    best_cid = None
    best_score = 0.0

    for cid, rep_title in cluster_rep.items():
        if cluster_size.get(cid, 0) >= MAX_CLUSTER_SIZE:
            continue
        
        # Cross-category prevention
        if category and cluster_cat.get(cid) and category != cluster_cat[cid]:
            continue

        vec2 = text_to_vector(rep_title)
        score = get_cosine(vec1, vec2)
        if score > threshold and score > best_score:
            best_score = score
            best_cid = cid

    return best_cid if best_cid else str(uuid.uuid4())[:8]

