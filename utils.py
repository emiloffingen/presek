import datetime
import math
from config import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY

def score_cluster(arts):
    """
    PageRank-style cluster importance score.
    Combines:
      - Source count (breadth of coverage)
      - Credibility-weighted source score
      - Recency (decays over 24h)
    """
    now = datetime.datetime.now()

    # Credibility score — sum of weights of unique sources
    unique_sources = {a["source"] for a in arts}
    cred_score = sum(
        SOURCE_CREDIBILITY.get(s, DEFAULT_CREDIBILITY)
        for s in unique_sources
    )

    # Recency score — exponential decay, half-life = 6 hours
    try:
        latest = datetime.datetime.fromisoformat(arts[0]["created_at"].replace("+00:00", ""))
        hours_old = (now - latest).total_seconds() / 3600
    except Exception:
        hours_old = 24
    recency = math.exp(-0.115 * hours_old)  # e^(-ln2/6 * h) ≈ halves every 6h

    # Source count bonus (logarithmic — diminishing returns)
    breadth = math.log1p(len(arts))

    # Click engagement bonus
    total_clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    click_bonus = 1 + math.log1p(total_clicks) * 0.15

    return cred_score * recency * breadth * click_bonus


def rank_articles_in_cluster(arts):
    """Within a cluster, put the most credible source first."""
    return sorted(
        arts,
        key=lambda a: SOURCE_CREDIBILITY.get(a["source"], DEFAULT_CREDIBILITY),
        reverse=True
    )
