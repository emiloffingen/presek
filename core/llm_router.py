import logging
import os
from nlp.categories import detect_topic
from nlp.generation import _extract_sports_scores

log = logging.getLogger("presek.router")


def _local_model_available() -> bool:
    configured_path = os.environ.get("LOCAL_MODEL_PATH")
    if configured_path:
        return os.path.exists(configured_path)
    return os.path.exists("models/gemma-4-E2B-it-Q4_K_M.gguf")


class SmartModelRouter:
    @staticmethod
    def route_cluster(articles: list[dict], lang: str = "sr") -> str:
        """
        Determines the optimal LLM provider or local fallback for a given news cluster.
        Returns one of: 'enhanced_fallback', 'local', 'mistral_small', 'mistral_large', 'nvidia'.
        """
        if not articles:
            return "enhanced_fallback"

        article_count = len(articles)
        all_titles = " ".join([a.get("title") or "" for a in articles])
        all_text = all_titles + " " + " ".join([a.get("description") or "" for a in articles])

        # 1. Sport check & sports score conflicts
        is_sport = detect_topic(all_titles) == "Sport" or any(bool(_extract_sports_scores(a.get("title") or "")) for a in articles)
        has_score_conflict = False
        if is_sport and article_count > 1:
            scores = [
                set(_extract_sports_scores(a.get("title") or "")) | set(_extract_sports_scores(a.get("description") or ""))
                for a in articles
            ]
            all_scores = set().union(*scores)
            conflicting_scores = [
                s for s in all_scores if sum(1 for ms in scores if s in ms) < len(articles)
            ]
            if conflicting_scores:
                has_score_conflict = True

        # 2. Political or economic weight check (requires deep analytical models)
        lowered_text = all_text.lower()
        political_terms = {
            "izbor", "glasanje", "vlada", "sobranie", "skupština", "парламент", "избор", "влада", "собрание", "mickos", "vucic"
        }
        economic_terms = {
            "cena", "inflacija", "budzet", "plata", "tržište", "ekonom", "цена", "инфлација", "буџет", "плата", "пазар"
        }
        
        has_high_weight = (
            any(term in lowered_text for term in political_terms) or
            any(term in lowered_text for term in economic_terms)
        )

        log.debug(f"[router] Routing info: count={article_count}, is_sport={is_sport}, score_conflict={has_score_conflict}, high_weight={has_high_weight}")

        local_available = _local_model_available()
        prefer_local_synthesis = os.environ.get("LOCAL_SYNTHESIS_PREFER_LOCAL", "true").lower() == "true"
        force_remote_high_complexity = (
            os.environ.get("LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE", "true").lower() == "true"
        )

        is_high_complexity = (
            article_count >= 5 or 
            has_score_conflict or 
            (article_count >= 3 and has_high_weight)
        )

        # --- Decision Matrix ---

        # If local is available, preferred, and it's NOT a high complexity story that we want to force remote for
        if local_available and prefer_local_synthesis and not (is_high_complexity and force_remote_high_complexity):
            return "local"
        
        # High Complexity: Serious disputes, large clusters, high political/economic weight, or sports conflicts
        if is_high_complexity:
            return "mistral_large"

        # Medium Complexity: Standard news, moderate cluster size
        if article_count >= 3 or has_high_weight:
            return "mistral_small"

        # Low Complexity: 1-2 articles, straightforward routine news
        # Always try Gemma 4 E2B first, then enhanced fallback
        # Gemma 4 E2B will handle its own fallback if model is not available
        return "local"
