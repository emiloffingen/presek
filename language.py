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
        with httpx.Client(timeout=30.0) as client:
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
    # Bulgarian-only vs MK: ъ, щ, ю, я (MK uses ј + vowel)
    bg_markers = sum(1 for ch in lower if ch in "ъщюя")
    
    # Serbian-only vs MK: ђ, ћ (MK uses ѓ, ќ)
    sr_markers = sum(1 for ch in lower if ch in "ђћ")

    if bg_markers >= 1: return "bg"
    if sr_markers >= 1: return "sr"

    # Bulgarian function words not used in MK
    # 'ще' is very strong BG (MK uses 'ќе')
    # 'бъде' is BG (MK uses 'биде')
    # 'върху' is BG (MK uses 'на')
    bg_words = sum(1 for w in ("също", "защото", "обаче", "няма",
                               "трябва", "която", "който", "което",
                               "ще", "бъде", "върху", "след")
                   if f" {w} " in f" {lower} ")
    if bg_words >= 1:
        return "bg"

    # Serbian function words not used in MK
    # 'da li' is very SR (MK uses 'дали')
    # 'tokom' is SR (MK uses 'за време на')
    sr_words = sum(1 for w in ("такође", "односно", "ипак",
                               "међутим", "након", "током",
                               "саопштио", "изјавио", "наводи")
                   if f" {w} " in f" {lower} ")
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
        labels, _probs = model.predict(cleaned, k=1)
        if labels:
            # Labels look like '__label__mk'
            return labels[0].replace("__label__", "")
    except Exception as e:
        log.warning(f"[language] fastText predict failed: {e}")
    return _script_heuristic(cleaned)


def is_macedonian(text: str) -> bool:
    return detect_language(text) == "mk"


def is_cyrillic_south_slavic(text: str) -> bool:
    """True for Macedonian/Bulgarian/Serbian (Cyrillic) — scripts that render
    naturally on Presek without translation."""
    return detect_language(text) in {"mk", "bg", "sr"}
