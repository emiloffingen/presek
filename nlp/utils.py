import html as _html
import json
import logging
import re
import threading
from collections import OrderedDict

log = logging.getLogger("presek")

_CLEAN_ARTIFACTS = [
    re.compile(r"Read\s+More\s*[»\>\-]*\s*$", re.I),
    re.compile(r"Procitaj\s+povece\s*$", re.I),
    re.compile(r"Continue\s+reading\s*$", re.I),
    re.compile(r"\[\s*&#\d+;\s*\]"),
    re.compile(r"\[\s*\.\.\.\s*\]"),
    re.compile(r"\s*&#8230;\s*$"),
    re.compile(r"\s*…\s*$"),
]


def cleanAndDecode(text: str) -> str:
    if not text:
        return ""
    cleaned = _html.unescape(str(text))
    for rx in _CLEAN_ARTIFACTS:
        cleaned = rx.sub("", cleaned)
    cleaned = re.sub(r"^[⚪🟢🔴]\s*", "", cleaned)
    cleaned = re.sub(r"#[^\s#]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


_JSON_SUMMARY_MARKERS = (
    '"summary"',
    '"synthetic_headline"',
    '"synthetic_standfirst"',
    '"generated_article"',
    '"key_facts"',
    '"perspectives"',
    "verification_report",
)

_JSON_STRING_FIELD_RE = r'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"'


def _decode_json_string_fragment(raw: str) -> str:
    try:
        return raw.encode("utf-8").decode("unicode-escape", errors="ignore")
    except Exception:
        return raw


def _unwrap_jsonish_string_field(text: str, field: str) -> str | None:
    pattern = _JSON_STRING_FIELD_RE.format(field=re.escape(field))
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return _decode_json_string_fragment(match.group(1))

    truncated = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    if truncated:
        return _decode_json_string_fragment(truncated.group(1))
    return None


def looks_like_leaked_json_fragment(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    lowered = clean.lower()
    marker_count = sum(1 for marker in _JSON_SUMMARY_MARKERS if marker in lowered)
    bullet_json_lines = sum(1 for line in clean.splitlines() if line.strip().startswith(("• {", '• "', "{", '"')))
    if marker_count >= 2 or bullet_json_lines >= 2:
        return True
    return clean.startswith("{") and '"summary"' in lowered


def extract_clean_summary_text(text: str) -> str:
    current = str(text or "")
    if not current.strip():
        return ""

    for _ in range(3):
        trimmed = current.strip()
        trimmed = re.sub(r"^```json\s*", "", trimmed, flags=re.I)
        trimmed = re.sub(r"```\s*$", "", trimmed).strip()

        if not (
            trimmed.startswith("{")
            or "&quot;summary&quot;" in trimmed
            or '"summary":' in trimmed
            or '"text":' in trimmed
        ):
            break

        decoded = cleanAndDecode(trimmed) if ("&quot;" in trimmed or "&lt;" in trimmed) else trimmed
        if decoded.startswith("{"):
            try:
                parsed = json.loads(decoded)
                if isinstance(parsed, dict):
                    next_val = parsed.get("summary") or parsed.get("text")
                    if next_val:
                        if isinstance(next_val, list):
                            current = "\n".join(f"• {item}" for item in next_val)
                        else:
                            current = str(next_val)
                        continue
            except Exception:
                extracted = _unwrap_jsonish_string_field(decoded, "summary") or _unwrap_jsonish_string_field(decoded, "text")
                if extracted:
                    current = extracted
                    continue
        break

    cleaned = cleanAndDecode(current)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
    return cleaned.strip()


_CYR_TO_LAT_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ѓ": "gj",
    "е": "e",
    "ж": "zh",
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
    "ќ": "kj",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "џ": "dzh",
    "ш": "sh",
    "ћ": "c",
    "ђ": "dj",
    "я": "ja",
    "ю": "ju",
    "щ": "sht",
    "ъ": "a",
}


def transliterate(text: str) -> str:
    """Transliterate Cyrillic to Latin for cross-script comparison."""
    if not text:
        return ""
    res = []
    for char in text:
        lower_char = char.lower()
        if lower_char in _CYR_TO_LAT_MAP:
            lat = _CYR_TO_LAT_MAP[lower_char]
            res.append(lat.upper() if char.isupper() else lat)
        else:
            res.append(char)
    return "".join(res)


def deShout(text: str) -> str:
    """Converts ALL CAPS text into Sentence case, preserving acronyms."""
    if not text:
        return ""
    s = str(text)
    # If text doesn't have many lowercase letters, it's probably shouting
    # Full Latin a-z + Cyrillic lowercase а-я plus special chars: ёѓќџљњћжшђч
    lowerCount = len(re.findall(r"[a-zа-яёѓќџљњћжшђч]", s))
    totalAlpha = len(re.findall(r"[a-zA-Zа-яА-ЯёЁѓЃќЌџЏљЉњЊћЋжЖшШђЂчЧ]", s))

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
        normalized.append(
            {
                "title": str(article.get("title") or "").strip(),
                "description": str(article.get("description") or "").strip(),
                "source": str(article.get("source") or "izvor").strip(),
                "link": article.get("link"),
                "created_at": article.get("created_at"),
                "category": article.get("category"),
                "country": article.get("country"),
            }
        )
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
