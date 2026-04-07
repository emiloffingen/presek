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
import urllib.request

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
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
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
    """Simple fallback: classify by dominant script."""
    if not text:
        return "unk"
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u04ff")
    lat = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if cyr == 0 and lat == 0:
        return "unk"
    return "mk" if cyr >= lat else "en"


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
