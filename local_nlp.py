from nlp import *
from nlp.keywords import _sentence_tokens, _extract_capitalized_phrases, ENTITY_NOISE_WORDS
from nlp.generation import _extract_number_tokens, _rank_cluster_question_evidence, _build_grounded_answer_from_evidence, _comparison_cache
from utils import record_runtime_event

def classify_news_quality_locally(title: str, description: str) -> dict:
    """
    Heuristic-based quality classifier for Macedonian news.
    Returns: {"score": float (0.0 to 1.0), "is_hard_news": bool, "reason": str}
    """
    text = (f"{title} {description or ''}").lower()
    
    # 1. Soft News / Junk Indicators
    soft_keywords = {
        "хороскоп", "хороскопот", "ѕвездите", "предвидуваат", "астро",
        "фустан", "мода", "изглед", "шокира", "скандал", "развод",
        "рецепт", "состојки", "кујна", "вкусна", "диета",
        "вирално", "хит", "социјалните мрежи", "тиктокер", "инфлуенсер",
        "видео", "фото", "галерија", "гледајте", "нема да верувате"
    }
    
    # 2. Hard News / High Value Indicators
    hard_keywords = {
        "собрание", "парламент", "влада", "министер", "премиер", "претседател",
        "закон", "устав", "буџет", "економија", "инфлација", "берза",
        "суд", "обвинителство", "истрага", "полиција", "криминал",
        "брисел", "еу", "нато", "вашингтон", "преговори",
        "инфраструктура", "изградба", "енергетика", "здравство"
    }

    # Count occurrences
    soft_matches = sum(1 for kw in soft_keywords if kw in text)
    hard_matches = sum(1 for kw in hard_keywords if kw in text)
    
    # 3. Entity Density Check (Hard news tends to have more unique named entities)
    potential_entities = _extract_capitalized_phrases(f"{title} {description or ''}")
    unique_entities = set(e.casefold() for e in potential_entities if e.casefold() not in ENTITY_NOISE_WORDS)
    entity_count = len(unique_entities)

    # Scoring Logic
    base_score = 0.5
    if hard_matches > 0: base_score += 0.1 * min(hard_matches, 3)
    if entity_count >= 3: base_score += 0.15
    if soft_matches > 0: base_score -= 0.25 * soft_matches
    
    # Clamp
    score = max(0.0, min(1.0, base_score))
    
    # Threshold for "Hard News" label
    is_hard = score >= 0.55
    
    reason = "Standard"
    if soft_matches > hard_matches: reason = "Soft Content"
    elif hard_matches > 2: reason = "High Value Policy/Event"
    elif entity_count > 4: reason = "Entity Rich"

    return {
        "score": round(score, 2),
        "is_hard_news": is_hard,
        "reason": reason,
        "entity_count": entity_count
    }
