import re
import logging

log = logging.getLogger("presek")

# Simple Macedonian Lexicon for Sentiment (Positive / Negative)
SENTIMENT_LEXICON = {
    # Positive - General & Politics
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
    # Negative - Crime, War, Crisis
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
}

NEGATIONS = {"ne", "nitu", "nikako", "bez", "prestana", "prekina", "protiv"}


def analyze_sentiment_locally(text):
    """
    Returns a score between -2.0 and 2.0 based on keyword frequency.
    Improved with negation detection.
    """
    if not text:
        return 0.0

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
