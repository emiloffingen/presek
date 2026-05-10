import re
import logging

log = logging.getLogger("presek")

# Simple Macedonian Lexicon for Sentiment (Positive / Negative)
SENTIMENT_LEXICON = {
    # Positive - General & Politics
    "добро": 1.0,
    "одлично": 2.0,
    "супер": 2.0,
    "успех": 1.5,
    "напредок": 1.5,
    "победа": 2.0,
    "развој": 1.0,
    "раст": 1.0,
    "стабилност": 1.5,
    "безбедност": 1.5,
    "хуманост": 1.5,
    "правда": 1.5,
    "слобода": 1.5,
    "демократија": 1.0,
    "поддршка": 1.0,
    "инвестиции": 1.5,
    "договор": 1.0,
    "соработка": 1.0,
    "реформи": 1.0,
    "награда": 1.5,
    "подобрување": 1.5,
    "спасени": 2.0,
    "изградба": 1.0,
    "позитивно": 1.5,
    "солидарност": 1.5,
    "донација": 1.5,
    "триумф": 2.0,
    "зголемување": 1.0,
    "европски": 0.5,
    "стандард": 1.0,
    "интеграција": 1.0,
    "надеж": 1.5,
    "одобрено": 1.0,
    # Negative - Crime, War, Crisis
    "лошо": -1.0,
    "катастрофа": -2.0,
    "криза": -1.5,
    "проблем": -1.0,
    "скандал": -2.0,
    "корупција": -2.0,
    "напад": -1.5,
    "војна": -2.0,
    "смрт": -2.0,
    "убиство": -2.0,
    "затвор": -1.5,
    "кражба": -1.5,
    "криминал": -2.0,
    "криминалци": -2.0,
    "неуспех": -1.5,
    "порази": -1.5,
    "поразот": -1.5,
    "загуба": -1.5,
    "критикува": -1.0,
    "осудува": -1.5,
    "неправда": -1.5,
    "хаос": -1.5,
    "смртност": -2.0,
    "болест": -1.5,
    "штета": -1.5,
    "закана": -1.5,
    "бомба": -2.0,
    "несреќа": -2.0,
    "пожар": -1.5,
    "судир": -1.5,
    "повредени": -1.5,
    "жртви": -2.0,
    "уапсен": -1.0,
    "уапсени": -1.0,
    "притвор": -1.0,
    "осомничен": -1.0,
    "насилство": -2.0,
    "престрелка": -1.5,
    "тензии": -1.5,
    "судење": -0.5,
    "инфлација": -1.5,
    "поскапување": -1.0,
    "штрајк": -1.0,
    "протест": -1.0,
    "оставка": -1.0,
    "трагедија": -2.0,
    "уценува": -1.5,
    "опаснo": -1.5,
    "опасност": -1.5,
    "загуби": -1.5,
    "колапс": -2.0,
    "пад": -1.0,
    "намалување": -0.5,
    "влошување": -1.5,
}

NEGATIONS = {"не", "ниту", "никако", "без", "престана", "прекина", "против"}


def analyze_sentiment_locally(text):
    """
    Returns a score between -2.0 and 2.0 based on keyword frequency.
    Improved with negation detection.
    """
    if not text:
        return 0.0

    words = re.findall(r"[А-Яа-яЀ-ӿ\w]{2,}", text.lower())
    score = 0.0
    matches = 0
    negate_next = False

    for w in words:
        if w in NEGATIONS:
            negate_next = True
            continue

        if w in SENTIMENT_LEXICON:
            val = SENTIMENT_LEXICON[w]
            if negate_next:
                val = -val * 0.8  # Flip and slightly damp
                negate_next = False

            score += val
            matches += 1
        else:
            # Reset negation if no sentiment word follows immediately
            negate_next = False

    if matches == 0:
        return 0.0

    # Normalize by matches but cap at 2.0
    final_score = score / matches
    return max(-2.0, min(2.0, final_score))
