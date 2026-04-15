"""
clustering.py — Advanced Hybrid News Clustering for Пресек
Combines Title Fingerprinting, Semantic (Vector) Search, and Weighted TF-IDF.
"""
import math, uuid, re
import datetime
from collections import Counter
from database import get_db

# ── Macedonian stemmer ────────────────────────────────────────────
MK_SUFFIXES = [
    "увањето", "ување", "ањето", "ање", "ењето", "ење",
    "истите", "истот", "иста", "исти", "ските", "скиот", "ската", "ски", "ска", "ско",
    "овските", "овскиот", "овската", "овски", "овска", "овско",
    "евските", "евскиот", "евската", "евски", "евска", "евско",
    "ните", "ниот", "ната", "ното", "ни", "ите", "иот", "ата", "ото", "от", "та", "то",
    "вме", "вте", "аа", "еа", "ше", "ат", "ет",
    "овиот", "овата", "овото", "ови", "ов", "ова", "ово",
    "евиот", "евата", "евото", "еви", "ев", "ева", "ево",
]

def mk_stem(word: str) -> str:
    if len(word) < 4: return word
    # Don't stem proper nouns (starts with capital) unless it's the very start of a sentence
    # but since we receive tokens, we'll be conservative.
    if word[0].isupper(): return word
    word = re.sub(r'[^\w\s]', '', word)
    
    # Strip common comparative/superlative prefixes
    if word.startswith("нај") and len(word) > 6:
        word = word[3:]
    elif word.startswith("по") and len(word) > 5:
        word = word[2:]
        
    for suffix in MK_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
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
    "туку","пак","сепак","затоа","бидејки","ваков","ваква","вакви",
    "the","and","for","from","that","this","with","has",
}

def _normalize_cluster_title(title: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(title or ""))
    text = re.sub(r"[\"'“”‘’`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text

def _get_fingerprint(title: str) -> str:
    """Create a minimal fingerprint for exact/near-exact title matches."""
    normalized = _normalize_cluster_title(title)
    words = re.findall(r'[А-Яа-яЀ-ӿ\w]+', normalized)
    # Sort words to catch permutated titles
    return "".join(sorted([w for w in words if w not in MK_STOPWORDS]))

def _title_terms(title: str) -> list[str]:
    normalized = _normalize_cluster_title(title)
    words = re.findall(r"[А-Яа-яЀ-ӿ\w]{3,}", normalized)
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

def _temporal_decay(created_at) -> float:
    """Stronger decay for older news to prevent clusters spanning weeks."""
    if not created_at: return 1.0
    if isinstance(created_at, str):
        try: created_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except: return 1.0
    
    now = datetime.datetime.now(datetime.timezone.utc)
    if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=datetime.timezone.utc)
    
    age_hours = (now - created_at).total_seconds() / 3600.0
    # Half-life of ~12 hours for clustering
    return math.exp(-0.05 * age_hours) 

def text_to_vector(text: str) -> Counter:
    words = re.findall(r'[А-Яа-яЀ-ӿ\w]{3,}', text.lower())
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
SIMILARITY_THRESHOLD = 0.48  # Tuned threshold
MAX_CLUSTER_SIZE     = 35
# Cosine-distance cutoff for pgvector semantic lookup. Tuned for the local
# paraphrase-multilingual-MiniLM-L12-v2 model (384-dim, L2-normalized):
# same-story pairs typically sit around 0.10–0.25, clearly-related topics
# 0.25–0.35, unrelated >0.45. 0.30 keeps precision high without being so
# strict that it misses near-duplicate stories from different sources.
VECTOR_THRESHOLD     = 0.30

def find_cluster_semantic(conn, embedding: list[float], lookback_hours: int = 36, category: str | None = None) -> str | None:
    if not embedding: return None
    try:
        # Adaptive threshold based on category diversity
        threshold = VECTOR_THRESHOLD
        if category in ("Свет", "Европа", "Балкан", "САД", "Америка", "Регион"):
            threshold = 0.22  # Stricter for international news
            
        params = [str(embedding), lookback_hours, str(embedding)]
        cat_filter = ""
        if category and category != 'Македонија':
            cat_filter = "AND a.category = %s"
            params.insert(1, category)

        # 1. Find the best candidate leveraging HNSW index
        sql = f"""
            SELECT a.cluster_id, a.embedding <=> %s::vector as distance
            FROM articles a
            WHERE a.embedding IS NOT NULL
              {cat_filter}
              AND a.created_at >= NOW() - %s * INTERVAL '1 hour'
            ORDER BY a.embedding <=> %s::vector
            LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
        
        if row and float(row['distance']) < threshold:
            # 2. Only check size for the single winner
            cid = row['cluster_id']
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) as n FROM articles WHERE cluster_id = %s", (cid,))
                size_row = cur.fetchone()
            if size_row and int(size_row['n']) < MAX_CLUSTER_SIZE:
                return cid
    except Exception as e:
        import logging
        logging.getLogger("presek").error(f"[clustering] Semantic lookup failed: {e}")
    return None

def find_or_create_cluster(conn, title: str, recent_articles: list, 
                            threshold: float = SIMILARITY_THRESHOLD,
                            embedding: list[float] | None = None,
                            category: str | None = None,
                            source: str | None = None) -> str:
    """
    Unified clustering pipeline:
    1. Title Fingerprinting (Instant match for same-story duplicates)
    2. Semantic Vector Match (local MiniLM embeddings via pgvector)
    3. Multi-representative TF-IDF with Entity & Recency Boosting
    """
    # 1. Title Fingerprinting
    input_fp = _get_fingerprint(title)
    
    # 2. Semantic Search
    if embedding:
        cid = find_cluster_semantic(conn, embedding, category=category)
        if cid: return cid

    # 3. TF-IDF Hybrid Fallback
    vec1 = text_to_vector(title)
    if not vec1: return str(uuid.uuid4())[:8]

    potential_entities = set(re.findall(r'[А-ЯЀ-ӿ][а-яѐ-ӿ]+', title))
    normalized_input = _normalize_cluster_title(title)

    cluster_docs = {}
    cluster_size = {}
    cluster_sources = {}
    all_cids = set()
    
    for article in recent_articles:
        cid = article.get("cluster_id")
        if not cid: continue
        all_cids.add(cid)
        cluster_size[cid] = cluster_size.get(cid, 0) + 1
        
        # Track sources to avoid grouping multiple articles from same source in same cluster (unless it's a series)
        cluster_sources.setdefault(cid, set()).add(article.get("source"))

        if cid not in cluster_docs:
            cluster_docs[cid] = []
        
        # Keep up to 3 diverse representatives for matching
        if len(cluster_docs[cid]) < 3:
            # Quick Fingerprint match check
            if input_fp and _get_fingerprint(article["title"]) == input_fp:
                return cid
            cluster_docs[cid].append(article)

    # Entity Fetching
    from database import db_manager
    cluster_entities = db_manager.get_cluster_entities(list(all_cids))

    best_cid = None
    best_score = 0.0

    for cid, reps in cluster_docs.items():
        if cluster_size.get(cid, 0) >= MAX_CLUSTER_SIZE: continue
        
        # Source Exclusivity: Penalty if source is already in cluster (prevents flood)
        source_penalty = 1.0
        if source and source in cluster_sources.get(cid, set()):
            source_penalty = 0.7 

        current_best_rep_score = 0.0
        for rep in reps:
            rep_title = rep["title"]
            lexical_score = get_cosine(vec1, text_to_vector(rep_title))
            phrase_score = _title_phrase_overlap(normalized_input, rep_title)
            
            # Weighted combine
            score = (lexical_score * 0.7) + (phrase_score * 0.3)
            score *= _temporal_decay(rep.get("created_at"))
            score *= source_penalty
            
            if score > current_best_rep_score:
                current_best_rep_score = score
        
        # Entity Boosting
        if cid in cluster_entities and potential_entities:
            shared = potential_entities.intersection(cluster_entities[cid])
            if shared:
                current_best_rep_score += min(0.25, len(shared) * 0.12)

        if current_best_rep_score > threshold and current_best_rep_score > best_score:
            best_score = current_best_rep_score
            best_cid = cid

    return best_cid if best_cid else str(uuid.uuid4())[:8]
