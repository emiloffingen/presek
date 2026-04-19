from nlp import *
from nlp.keywords import _sentence_tokens, _extract_capitalized_phrases, ENTITY_NOISE_WORDS
from nlp.generation import _extract_number_tokens, _rank_cluster_question_evidence, _build_grounded_answer_from_evidence, _comparison_cache
from utils import record_runtime_event

def classify_news_quality_locally(title: str, description: str) -> dict:
    """
    Advanced Heuristic-based quality classifier for Macedonian news.
    Favors standard literary patterns and penalizes 'internet slang' or 'noise'.
    """
    text = (f"{title} {description or ''}").lower()
    
    # 1. High-Value / Hard News Indicators (Policy, Law, Infrastructure)
    hard_keywords = {
        "собрание", "парламент", "влада", "министер", "премиер", "претседател",
        "закон", "устав", "буџет", "економија", "инфлација", "берза",
        "суд", "обвинителство", "истрага", "полиција", "криминал",
        "брисел", "еу", "нато", "вашингтон", "преговори",
        "инфраструктура", "изградба", "енергетика", "здравство", "образование"
    }
    
    # 2. Low-Value / Junk Indicators
    soft_keywords = {
        "хороскоп", "хороскопот", "ѕвездите", "предвидуваат", "астро",
        "фустан", "мода", "изглед", "шокира", "скандал", "развод",
        "рецепт", "состојки", "кујна", "вкусна", "диета",
        "вирално", "хит", "социјалните мрежи", "тиктокер", "инфлуенсер",
        "фото", "галерија", "гледајте", "нема да верувате"
    }

    # 3. Literacy / Professionalism Penalties
    # Penalize non-standard spelling or "shouting" punctuation
    literacy_penalty = 0.0
    if "!!!" in text or "???" in text: literacy_penalty += 0.2
    if "шокантно" in text or "скандалозно" in text: literacy_penalty += 0.15
    
    # Check for informal particles/slang common in low-quality portals
    if any(s in text for s in ["еве што", "како да", "само што"]): literacy_penalty += 0.1

    # 4. Entity Density Check (Hard news has more unique named entities)
    potential_entities = _extract_capitalized_phrases(f"{title} {description or ''}")
    unique_entities = set(e.casefold() for e in potential_entities if e.casefold() not in ENTITY_NOISE_WORDS)
    entity_count = len(unique_entities)

    # 5. Scoring Logic
    hard_matches = sum(1 for kw in hard_keywords if kw in text)
    soft_matches = sum(1 for kw in soft_keywords if kw in text)
    
    base_score = 0.5
    if hard_matches > 0: base_score += 0.12 * min(hard_matches, 3)
    if entity_count >= 3: base_score += 0.15
    if soft_matches > 0: base_score -= 0.3 * soft_matches
    
    # Apply Literacy Penalty
    base_score -= literacy_penalty
    
    # Final clamping
    score = max(0.0, min(1.0, base_score))
    
    reason = "Standard"
    if score < 0.35: reason = "Low Quality / Junk"
    elif soft_matches > hard_matches: reason = "Soft Content"
    elif hard_matches > 2: reason = "High Value Policy/Event"
    elif entity_count > 4: reason = "Entity Rich"

    return {
        "score": round(score, 2),
        "is_hard_news": score >= 0.55,
        "reason": reason,
        "entity_count": entity_count,
        "penalties": round(literacy_penalty, 2)
    }
