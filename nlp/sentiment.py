import logging
import re

log = logging.getLogger("presek")

# Bilingual Macedonian + Serbian Lexicon for Sentiment (Positive / Negative)
SENTIMENT_LEXICON = {
    # Positive - General & Politics (Macedonian)
    "dobro": 1.0,
    "odlicno": 2.0,
    "super": 2.0,
    "uspeh": 1.5,
    "napredok": 1.5,
    "pobeda": 2.0,
    "razvoj": 1.0,
    "rast": 1.0,
    "stabilnost": 1.5,
    "bezbednost": 1.5,
    "humanost": 1.5,
    "pravda": 1.5,
    "sloboda": 1.5,
    "demokratija": 1.0,
    "poddrska": 1.0,
    "investicii": 1.5,
    "dogovor": 1.0,
    "sorabotka": 1.0,
    "reformi": 1.0,
    "nagrada": 1.5,
    "podobruvanje": 1.5,
    "spaseni": 2.0,
    "izgradba": 1.0,
    "pozitivno": 1.5,
    "solidarnost": 1.5,
    "donacija": 1.5,
    "triumf": 2.0,
    "zgolemuvanje": 1.0,
    "evropski": 0.5,
    "standard": 1.0,
    "integracija": 1.0,
    "nadez": 1.5,
    "odobreno": 1.0,
    # Positive - Serbian specific
    "uspešno": 1.5,
    "uspesno": 1.5,
    "saradnja": 1.0,
    "investicije": 1.5,
    "reforme": 1.0,
    "izgradnja": 1.0,
    "poboljšanje": 1.5,
    "poboljsanje": 1.5,
    "podrška": 1.0,
    "podrska": 1.0,
    "pozitivan": 1.5,
    "nada": 1.5,
    "odobrenje": 1.0,
    "unapređenje": 1.5,
    "unapredjenje": 1.5,
    "prosperitet": 1.5,
    "napredak": 1.5,
    # Negative - Crime, War, Crisis (Macedonian)
    "loso": -1.0,
    "katastrofa": -2.0,
    "kriza": -1.5,
    "problem": -1.0,
    "skandal": -2.0,
    "korupcija": -2.0,
    "napad": -1.5,
    "vojna": -2.0,
    "smrt": -2.0,
    "ubistvo": -2.0,
    "zatvor": -1.5,
    "krazba": -1.5,
    "kriminal": -2.0,
    "kriminalci": -2.0,
    "neuspeh": -1.5,
    "porazi": -1.5,
    "porazot": -1.5,
    "zaguba": -1.5,
    "kritikuva": -1.0,
    "osuduva": -1.5,
    "nepravda": -1.5,
    "haos": -1.5,
    "smrtnost": -2.0,
    "bolest": -1.5,
    "steta": -1.5,
    "zakana": -1.5,
    "bomba": -2.0,
    "nesreca": -2.0,
    "pozar": -1.5,
    "sudir": -1.5,
    "povredeni": -1.5,
    "zrtvi": -2.0,
    "uapsen": -1.0,
    "uapseni": -1.0,
    "pritvor": -1.0,
    "osomnicen": -1.0,
    "nasilstvo": -2.0,
    "prestrelka": -1.5,
    "tenzii": -1.5,
    "sudenje": -0.5,
    "inflacija": -1.5,
    "poskapuvanje": -1.0,
    "strajk": -1.0,
    "protest": -1.0,
    "ostavka": -1.0,
    "tragedija": -2.0,
    "ucenuva": -1.5,
    "opasno": -1.5,
    "opasnost": -1.5,
    "zagubi": -1.5,
    "kolaps": -2.0,
    "pad": -1.0,
    "namaluvanje": -0.5,
    "vlosuvanje": -1.5,
    # Negative - Serbian specific
    "šteta": -1.5,
    "nesreća": -2.0,
    "požar": -1.5,
    "povređeni": -1.5,
    "žrtve": -2.0,
    "uhapšen": -1.0,
    "uhapsen": -1.0,
    "suđenje": -0.5,
    "sudjenje": -0.5,
    "poskupljenje": -1.0,
    "neuspešno": -1.5,
    "neuspesno": -1.5,
    "poraz": -1.5,
    "gubitak": -1.5,
    "pretnja": -1.5,
    "nasilje": -2.0,
    "hapšenje": -1.0,
    "hapsenje": -1.0,
    "rat": -2.0,
    "loše": -1.0,
    "lose": -1.0,
    "pogoršanje": -1.5,
    "pogorsanje": -1.5,
    "smanjenje": -0.5,
}

NEGATIONS = {"ne", "nitu", "nikako", "bez", "prestana", "prekina", "protiv", "nije", "nema", "nikad"}


def analyze_sentiment_locally(text, bypass_llm: bool = False):
    """
    Returns a score between -2.0 and 2.0 based on local LLM or keyword frequency.
    Tries to utilize the local Gemma 4 model first for deep context understanding,
    falling back transparently to traditional lexicon keyword frequency.
    """
    if not text:
        return 0.0

    # 1. Try local LLM sentiment analysis first
    import os

    if not bypass_llm and os.environ.get("LOCAL_MODEL_PATH"):
        try:
            from nlp.local_analyst import LocalAnalyst

            analyst = LocalAnalyst()
            if analyst._load_model():
                from core.language import detect_language

                lang = detect_language(text)
                if lang == "sr":
                    system = (
                        "Ti si model za analizu sentimenta. Proceni sentiment teksta. "
                        "Vrati ISKLJUČIVO broj između -2.0 (ekstremno negativan/kritičan) i 2.0 (ekstremno pozitivan/afirmativan). "
                        "Neutralan sentiment treba da bude 0.0. Vrati samo broj bez ikakvog dodatnog teksta ili obrazloženja."
                    )
                else:
                    system = (
                        "Ti si model za analiza na sentiment. Proceni go sentimentot na tekstot. "
                        "Vrati ISKLUCIVO broj megu -2.0 (ekstremno negativen/kritican) i 2.0 (ekstremno pozitiven/afirmativen). "
                        "Neutralen sentiment treba da bide 0.0. Vrati samo broj bez nikakov dopolnitelen tekst ili obrazlozenie."
                    )

                res = analyst.analyze(text[:1200], system, max_tokens=10, lang=lang)
                if res:
                    match = re.search(r"[-+]?\d*\.\d+|\d+", res)
                    if match:
                        val = float(match.group())
                        return max(-2.0, min(2.0, val))
        except Exception as e:
            log.warning(f"[sentiment] Local LLM sentiment analysis failed: {e}. Falling back to lexicon.")

    # 2. Traditional Lexicon Fallback
    words = re.findall(r"[A-Za-z\w]{2,}", text.lower())
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
