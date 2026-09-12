"""
language.py — Fast language identification for Presek.

Uses fastText's compressed lid.176.ftz model (~917 KB, 176 languages) for
microsecond-level detection on CPU. Falls back to a Cyrillic/Latin script
heuristic if fastText or the model file is unavailable.

The model file is downloaded lazily on first use from:
    https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz
and cached at ~/.cache/fasttext/lid.176.ftz so subsequent runs are offline.
"""

import logging
import os
import threading

log = logging.getLogger("presek")

_MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
_CACHE_DIR = os.path.expanduser("~/.cache/fasttext")
_MODEL_PATH = os.path.join(_CACHE_DIR, "lid.176.ftz")

_model = None
_lock = threading.Lock()
_unavailable = False


def _ensure_model_file() -> str | None:
    if os.path.exists(_MODEL_PATH):
        return _MODEL_PATH
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        log.info(f"[language] Downloading fastText lid.176.ftz (~917 KB) to {_MODEL_PATH}")
        import httpx
        from core.http_pool import get_shared_client
        client = get_shared_client()
        with open(_MODEL_PATH, "wb") as f:
                with client.stream("GET", _MODEL_URL, follow_redirects=True) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        return _MODEL_PATH
    except Exception as e:
        log.warning(f"[language] Failed to download fastText model: {e}")
        return None


def _get_model():
    global _model, _unavailable
    if _unavailable:
        return None
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            import fasttext
        except ImportError:
            log.info("[language] fasttext not installed, using script heuristic")
            _unavailable = True
            return None
        path = _ensure_model_file()
        if not path:
            _unavailable = True
            return None
        try:
            # Suppress fastText's noisy C++ banner
            fasttext.FastText.eprint = lambda *a, **k: None
            _model = fasttext.load_model(path)
            log.info("[language] fastText lid.176.ftz loaded")
        except Exception as e:
            log.warning(f"[language] Failed to load fastText model: {e}")
            _unavailable = True
            return None
        return _model


def _script_heuristic(text: str) -> str:
    """Fallback: classify by script and characteristic markers."""
    if not text:
        return "unk"
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u04ff")
    lat = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if cyr == 0 and lat == 0:
        return "unk"
    if lat > cyr:
        return _latin_heuristic(text)
    return _cyrillic_heuristic(text)


def _cyrillic_heuristic(text: str) -> str:
    """Distinguish Macedonian from Bulgarian and Serbian in Cyrillic text."""
    lower = text.lower()

    # Unique letters check (Strongest signal)
    # Bulgarian-only vs RS: ъ, щ, ю, я (RS uses j + vowel)
    bg_markers = sum(1 for ch in lower if ch in "ъщюя")

    # Serbian-only vs RS: ђ, ћ (RS uses Dj, c)
    sr_markers = sum(1 for ch in lower if ch in "ђћ")

    if bg_markers >= 1:
        return "bg"
    if sr_markers >= 1:
        return "sr"

    # Bulgarian function words not used in RS
    # 'щe' is very strong BG (RS uses 'ce')
    # 'bъde' is BG (RS uses 'bide')
    # 'vъrhu' is BG (RS uses 'na')
    bg_words = sum(
        1
        for w in (
            "sъщo",
            "zaщoto",
            "obace",
            "nяma",
            "trяbva",
            "koяto",
            "koйto",
            "koeto",
            "щe",
            "bъde",
            "vъrhu",
            "sled",
        )
        if f" {w} " in f" {lower} "
    )
    if bg_words >= 1:
        return "bg"

    # Serbian function words not used in RS
    # 'da li' is very SR (RS uses 'dali')
    # 'tokom' is SR (RS uses 'za vreme na')
    sr_words = sum(
        1
        for w in (
            "takoђe",
            "odnosno",
            "ipak",
            "meђutim",
            "nakon",
            "tokom",
            "saopstio",
            "izjavio",
            "navodi",
        )
        if f" {w} " in f" {lower} "
    )
    if sr_words >= 1:
        return "sr"

    return "mk"


def _latin_heuristic(text: str) -> str:
    """Distinguish between Latin-script Balkan languages and English."""
    lower = text.lower()
    # Croatian/Bosnian diacritics: č, ć, đ, š, ž
    balkan_diacritics = sum(1 for ch in lower if ch in "čćđšž")
    if balkan_diacritics >= 1:
        return "hr"
    # Turkish markers: ğ, ş, ı, ö, ü (check before Albanian since ç is shared)
    turkish_chars = sum(1 for ch in lower if ch in "ğşı")
    if turkish_chars >= 1:
        return "tr"
    # Albanian markers: ë, ç and common words
    if "ë" in lower or "ç" in lower:
        return "sq"
    return "en"


def detect_language(text: str) -> str:
    """
    Returns an ISO 639-1 language code (e.g. 'mk', 'en', 'sr', 'bg').
    Returns 'unk' if detection fails entirely.
    """
    if not text or not text.strip():
        return "unk"
    # fastText is sensitive to newlines — it treats them as document separators
    cleaned = " ".join(text.split())[:2000]

    model = _get_model()
    if model is None:
        return _script_heuristic(cleaned)

    try:
        labels, _probs = model.predict([cleaned], k=1)
        if labels and labels[0]:
            # Labels look like [['__label__mk']]
            return labels[0][0].replace("__label__", "")
    except Exception as e:
        log.warning(f"[language] fastText predict failed: {e}")
    return _script_heuristic(cleaned)


def is_macedonian(text: str) -> bool:
    return detect_language(text) == "mk"


def is_cyrillic_south_slavic(text: str) -> bool:
    """True for Macedonian/Bulgarian/Serbian/Croatian/Bosnian — languages that
    render naturally on Presek without translation."""
    return detect_language(text) in {"mk", "bg", "sr", "hr", "bs"}


_CYR_LAT_MAP = {
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Ѓ": "Đ",
    "Е": "E",
    "Ж": "Ž",
    "З": "Z",
    "Ѕ": "Dz",
    "И": "I",
    "Ј": "J",
    "К": "K",
    "Л": "L",
    "Љ": "Lj",
    "М": "M",
    "Н": "N",
    "Њ": "Nj",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "Ќ": "Ć",
    "У": "U",
    "Ф": "F",
    "Х": "H",
    "Ц": "C",
    "Ч": "Č",
    "Џ": "Dž",
    "Ш": "Š",
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ѓ": "đ",
    "е": "e",
    "ж": "ž",
    "з": "z",
    "ѕ": "dz",
    "и": "i",
    "ј": "j",
    "к": "k",
    "л": "l",
    "љ": "lj",
    "м": "m",
    "н": "n",
    "њ": "nj",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "ќ": "ć",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "č",
    "џ": "dž",
    "ш": "š",
    "ћ": "ć",
    "Ћ": "Ć",
    "ђ": "đ",
    "Ђ": "Đ",
}


def transliterate_cyr_to_lat(text: str) -> str:
    """Standard South Slavic Cyrillic to Latin transliteration (case-preserving)."""
    if not text:
        return ""
    return "".join(_CYR_LAT_MAP.get(c, c) for c in text)


def transliterate_lat_to_cyr(text: str) -> str:
    """Standard Latin to Macedonian Cyrillic transliteration."""
    if not text:
        return ""
    
    # Check if it already has significant Cyrillic
    cyr_chars = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    if cyr_chars > 0:
        return text

    # Standardize vecer to вечер (case-insensitive) to ensure correct transliteration to вечер instead of вецер
    import re
    def replace_vecer(match):
        m = match.group(0)
        if m == 'VECER':
            return 'ВЕЧЕР'
        if m == 'Vecer':
            return 'Вечер'
        if m[0] == 'V':
            return 'Вечер'
        return 'вечер'
    res = re.sub(r'vecer', replace_vecer, text, flags=re.IGNORECASE)

    # Build reverse map, sorting by length descending to handle multi-char sequences like 'Dzh'
    lat_to_cyr_map = {v: k for k, v in _CYR_LAT_MAP.items()}
    digraphs = {
        "sh": "ш", "Sh": "Ш", "SH": "Ш",
        "zh": "ж", "Zh": "Ж", "ZH": "Ж",
        "ch": "ч", "Ch": "Ч", "CH": "Ч",
        "dj": "ѓ", "Dj": "Ѓ", "DJ": "Ѓ",
        "dz": "ѕ", "Dz": "Ѕ", "DZ": "Ѕ",
        "lj": "љ", "Lj": "Љ", "LJ": "Љ",
        "nj": "њ", "Nj": "Њ", "NJ": "Њ"
    }
    lat_to_cyr_map.update(digraphs)
    
    res = res.replace("ć", "c").replace("č", "ch").replace("š", "sh").replace("ž", "zh").replace("đ", "dj").replace("Ć", "C").replace("Č", "Ch").replace("Š", "Sh").replace("Ž", "Zh").replace("Đ", "Dj")
    for k in sorted(lat_to_cyr_map.keys(), key=len, reverse=True):
        res = res.replace(k, lat_to_cyr_map[k])
    return res
