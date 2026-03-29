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

# ── Macedonian stemmer ────────────────────────────────────────────
# Strip common definite article suffixes and adjectival endings
# Order matters — longer suffixes first
MK_SUFFIXES = [
    # Definite article forms (longest first)
    "увањето", "ување",
    "ањето",   "ање",
    "ењето",   "ење",
    "истите",  "истот", "иста", "исти",
    "ските",   "скиот", "ската", "ски", "ска", "ско",
    "ните",    "ниот",  "ната",  "ното", "ни",
    "ите",     "иот",   "ата",   "ото",
    "от",      "та",    "то",
]

def mk_stem(word: str) -> str:
    """Strip Macedonian inflectional suffixes. Returns stem."""
    if len(word) < 5:
        return word
    for suffix in MK_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word

# Common Macedonian stopwords to exclude from vectors
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
    """Tokenize, stem, and remove stopwords."""
    words = re.findall(r'[а-шА-Ш\w]{3,}', text.lower())
    stems = [mk_stem(w) for w in words if w not in MK_STOPWORDS]
    return Counter(stems)

def get_cosine(vec1: Counter, vec2: Counter) -> float:
    intersection = set(vec1) & set(vec2)
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(v**2 for v in vec1.values())
    sum2 = sum(v**2 for v in vec2.values())
    denom = math.sqrt(sum1) * math.sqrt(sum2)
    if not denom:
        return 0.0
    return numerator / denom

# ── Clustering parameters ─────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.35   # was 0.15 — raised to prevent false merges
MAX_CLUSTER_SIZE     = 30     # cap: once a cluster has this many articles, stop adding

def find_or_create_cluster(title: str, recent_articles: list,
                            threshold: float = SIMILARITY_THRESHOLD) -> str:
    """
    Find a matching cluster or create a new one.

    Strategy: 
    1. Dynamic Thresholding: Existing clusters are slightly easier to match (-0.05) 
       than creating a new one, favoring consolidation.
    2. Recency Decay: The threshold increases as the representative article gets older,
       preventing 'infinite clusters' for recurring generic topics.
    3. Representative Matching: Compares against the first article of each cluster.
    """
    vec1 = text_to_vector(title)
    if not vec1:
        return str(uuid.uuid4())[:8]

    # Build cluster representatives + sizes + ages from recent articles
    cluster_rep: dict[str, str] = {}      # cid -> representative title
    cluster_size: dict[str, int] = {}     # cid -> count
    cluster_age: dict[str, float] = {}    # cid -> hours since representative was created
    
    now = datetime.datetime.now()

    for article in recent_articles:
        cid = article.get("cluster_id", "")
        if not cid:
            continue
        cluster_size[cid] = cluster_size.get(cid, 0) + 1
        if cid not in cluster_rep:
            cluster_rep[cid] = article["title"]
            # Calculate age of the representative
            try:
                ts = article.get("created_at")
                if isinstance(ts, datetime.datetime):
                    dt = ts.replace(tzinfo=None)
                elif isinstance(ts, str):
                    dt = datetime.datetime.fromisoformat(ts.replace("+00:00", "").split('.')[0]) # Remove subseconds/timezone
                else:
                    dt = now
                cluster_age[cid] = (now - dt).total_seconds() / 3600
            except:
                cluster_age[cid] = 12 # fallback

    # Compare against each cluster representative
    best_cid = None
    best_score = 0.0

    for cid, rep_title in cluster_rep.items():
        # Skip full clusters
        if cluster_size.get(cid, 0) >= MAX_CLUSTER_SIZE:
            continue
            
        # 1. Dynamic threshold (favor existing)
        # 2. Recency penalty (older clusters are harder to match)
        age = cluster_age.get(cid, 12)
        penalty = (age / 24.0) * 0.1  # +0.1 threshold every 24 hours
        current_threshold = threshold - 0.05 + penalty
        
        vec2 = text_to_vector(rep_title)
        score = get_cosine(vec1, vec2)
        
        if score > current_threshold and score > best_score:
            best_score = score
            best_cid = cid

    return best_cid if best_cid else str(uuid.uuid4())[:8]
