import re
import html as _html
import logging
import threading
from collections import OrderedDict
from utils import record_runtime_event

log = logging.getLogger("presek")

_CLEAN_ARTIFACTS = [
    re.compile(r'Read\s+More\s*[»\>\-]*\s*$', re.I),
    re.compile(r'Прочитај\s+повеќе\s*$', re.I),
    re.compile(r'Continue\s+reading\s*$', re.I),
    re.compile(r'\[\s*&#\d+;\s*\]'),
    re.compile(r'\[\s*\.\.\.\s*\]'),
    re.compile(r'\s*&#8230;\s*$'),
    re.compile(r'\s*…\s*$'),
]

def cleanAndDecode(text: str) -> str:
    if not text:
        return ''
    cleaned = _html.unescape(str(text))
    for rx in _CLEAN_ARTIFACTS:
        cleaned = rx.sub('', cleaned)
    cleaned = re.sub(r'^[⚪🟢🔴]\s*', '', cleaned)
    cleaned = re.sub(r'#[^\s#]+', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def deShout(text: str) -> str:
    """Converts ALL CAPS text into Sentence case, preserving acronyms."""
    if not text: return ''
    s = str(text)
    # If text doesn't have many lowercase letters, it's probably shouting
    lowerCount = len(re.findall(r'[a-zа-ш]', s))
    totalAlpha = len(re.findall(r'[a-zA-Zа-шА-Ш]', s))
    
    if totalAlpha > 5 and lowerCount < totalAlpha * 0.2:
        return s.lower().capitalize()
    return s

_LOCAL_CACHE_MAXSIZE = 256
_local_cache_lock = threading.Lock()

_comparison_cache = OrderedDict()
_question_evidence_cache = OrderedDict()

def _freeze_cache_value(value):
    if isinstance(value, dict):
        return tuple((key, _freeze_cache_value(val)) for key, val in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_cache_value(item) for item in value)
    return value

def _thaw_cache_value(value):
    if isinstance(value, tuple):
        if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {key: _thaw_cache_value(val) for key, val in value}
        return [_thaw_cache_value(item) for item in value]
    return value

def _cache_get(store, key):
    with _local_cache_lock:
        if key not in store:
            return None
        frozen = store.pop(key)
        store[key] = frozen
    return _thaw_cache_value(frozen)

def _cache_set(store, key, value):
    with _local_cache_lock:
        if key in store:
            store.pop(key)
        store[key] = _freeze_cache_value(value)
        while len(store) > _LOCAL_CACHE_MAXSIZE:
            store.popitem(last=False)

def _normalize_articles_for_local_use(articles):
    normalized = []
    for article in articles or []:
        normalized.append({
            "title": str(article.get("title") or "").strip(),
            "description": str(article.get("description") or "").strip(),
            "source": str(article.get("source") or "Извор").strip(),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "category": article.get("category"),
        })
    return [article for article in normalized if article["title"]]

def _articles_cache_key(articles):
    normalized = _normalize_articles_for_local_use(articles)
    return tuple(
        (
            str(article.get("source") or "").strip(),
            str(article.get("title") or "").strip(),
            str(article.get("description") or "").strip(),
        )
        for article in normalized
    )
