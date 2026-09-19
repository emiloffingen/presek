"""Small deterministic sentiment scorer used when local AI is unavailable."""

POSITIVE = {"успех", "успешно", "победа", "победи", "раст", "поддршка", "напредок", "добро", "добар"}
NEGATIVE = {"криза", "напад", "смрт", "загуба", "пад", "проблем", "скандал", "закана", "лошо", "лош"}


def analyze_sentiment_locally(text: str, *args, **kwargs) -> float:
    tokens = set(str(text or "").casefold().split())
    positive = len(tokens & POSITIVE)
    negative = len(tokens & NEGATIVE)
    if not positive and not negative:
        return 0.0
    return max(-1.0, min(1.0, (positive - negative) / max(positive + negative, 1)))
