"""
nllb_translate.py — Self-hosted NLLB-200 translation for Presek.

Uses Meta's NLLB-200-distilled-600M model for translating Balkan and other
languages into Macedonian. The model is loaded lazily on first use and kept
in memory for subsequent calls.

Runs on CPU with ~2.5 GB RAM. Typical headline translation takes 5-10s.
Supports batching for higher throughput during ingestion cycles.
"""
import logging
import threading
import time
import re
import json
import hashlib
from hf_cache import configure_huggingface_cache

log = logging.getLogger("presek")

_model = None
_tokenizer = None
_lock = threading.Lock()
_unavailable = False

MODEL_NAME = "facebook/nllb-200-distilled-600M"
TARGET_LANG = "mkd_Cyrl"

# NLLB-200 language codes for Presek's source languages
LANG_CODES = {
    "sr": "srp_Cyrl",
    "bg": "bul_Cyrl",
    "hr": "hrv_Latn",
    "sq": "sqi_Latn",
    "bs": "bos_Latn",
    "en": "eng_Latn",
    "tr": "tur_Latn",
    "sl": "slv_Latn",
    "de": "deu_Latn",
    "fr": "fra_Latn",
    "it": "ita_Latn",
    "es": "spa_Latn",
    "el": "ell_Grek",
    "ro": "ron_Latn",
    "mk": "mkd_Cyrl",
}


configure_huggingface_cache()

def _get_redis():
    try:
        from utils import redis_client
        return redis_client
    except Exception:
        return None

def _load_model():
    """Load NLLB model and tokenizer. Called once, lazily."""
    global _model, _tokenizer, _unavailable
    if _unavailable:
        return None, None
    if _model is not None:
        return _model, _tokenizer
    with _lock:
        if _model is not None:
            return _model, _tokenizer
        try:
            t0 = time.time()
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
            log.info(f"[nllb] Model loaded in {time.time()-t0:.1f}s")
        except Exception as e:
            log.error(f"[nllb] Failed to load model: {e}")
            _unavailable = True
            return None, None
    return _model, _tokenizer

def _mask_entities(text: str) -> tuple[str, dict[str, str]]:
    """Protects capitalized phrases from translation by replacing them with placeholders."""
    from nlp.keywords import _extract_capitalized_phrases
    entities = _extract_capitalized_phrases(text)
    mapping = {}
    masked_text = text
    
    # Sort by length descending to avoid partial replacements
    for idx, ent in enumerate(sorted(set(entities), key=len, reverse=True)):
        placeholder = f"$[{idx}]$"
        mapping[placeholder] = ent
        masked_text = masked_text.replace(ent, placeholder)
        
    return masked_text, mapping

def _unmask_entities(text: str, mapping: dict[str, str]) -> str:
    """Restores masked entities in translated text with flexible matching."""
    if not text: return text
    unmasked = text
    for placeholder, original in mapping.items():
        # Handle cases where NLLB might have added spaces: $ [ 0 ] $
        # and escape $ and []
        idx = placeholder.strip("$[]")
        pattern = rf"\$\s*\[\s*{idx}\s*\]\s*\$"
        unmasked = re.sub(pattern, original, unmasked)
    return unmasked

def translate(text: str, src_lang: str, target_lang: str = "mk", use_cache: bool = True, mask_entities: bool = True) -> str | None:
    """Translate a single text from src_lang to target_lang.

    Includes Semantic Caching and Entity Masking.
    """
    if not text or not text.strip():
        return text

    # 1. Check Cache
    redis = _get_redis()
    cache_key = None
    if use_cache and redis:
        h = hashlib.md5(f"{text}:{src_lang}:{target_lang}".encode()).hexdigest()
        cache_key = f"nllb:trans:{h}"
        try:
            cached = redis.get(cache_key)
            if cached:
                if isinstance(cached, bytes):
                    return cached.decode('utf-8')
                return str(cached)
        except Exception as e:
            log.warning(f"[nllb] Cache read error: {e}")

    # 2. Entity Masking
    mask_map = {}
    working_text = text
    if mask_entities:
        working_text, mask_map = _mask_entities(text)

    model, tokenizer = _load_model()
    if model is None:
        return None

    src_code = LANG_CODES.get(src_lang)
    target_code = LANG_CODES.get(target_lang)
    if not src_code or not target_code:
        log.warning(f"[nllb] Unsupported language pair: {src_lang}→{target_lang}")
        return None

    try:
        tokenizer.src_lang = src_code
        inputs = tokenizer(working_text[:800], return_tensors="pt", truncation=True, max_length=400)
        translated = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids(target_code),
            max_new_tokens=400,
            num_beams=4,
            repetition_penalty=1.1,
        )
        result = tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
        
        if result:
            result = result.strip()
            # 3. Unmask
            if mask_entities:
                result = _unmask_entities(result, mask_map)
            
            # 4. Save to Cache (24h)
            if cache_key and redis:
                try:
                    redis.setex(cache_key, 86400, result)
                except Exception:
                    pass
            return result
        return None
    except Exception as e:
        log.error(f"[nllb] Translation failed ({src_lang}→{target_lang}): {e}")
        return None


def translate_batch(texts: list[str], src_langs: list[str], target_lang: str = "mk", mask_entities: bool = True) -> list[str | None]:
    """Translate multiple texts, potentially with different source languages."""
    if not texts:
        return []

    # For batch, we simplify and bypass complex masking for now to avoid alignment issues,
    # OR we implement it carefully. Let's do a simpler per-item loop for safety if masking is on.
    if mask_entities:
        return [translate(t, s, target_lang, mask_entities=True) for t, s in zip(texts, src_langs)]

    model, tokenizer = _load_model()
    if model is None:
        return [None] * len(texts)

    target_code = LANG_CODES.get(target_lang)
    if not target_code:
        log.warning(f"[nllb] Unsupported target language: {target_lang}")
        return [None] * len(texts)

    results = [None] * len(texts)

    # Group by source language for batching
    by_lang: dict[str, list[tuple[int, str]]] = {}
    for i, (text, lang) in enumerate(zip(texts, src_langs)):
        if not text or not text.strip():
            results[i] = text
            continue
        code = LANG_CODES.get(lang)
        if not code:
            continue
        by_lang.setdefault(code, []).append((i, text[:800]))

    for src_code, items in by_lang.items():
        try:
            tokenizer.src_lang = src_code
            batch_texts = [t for _, t in items]
            inputs = tokenizer(batch_texts, return_tensors="pt", padding=True,
                             truncation=True, max_length=400)
            translated = model.generate(
                **inputs,
                forced_bos_token_id=tokenizer.convert_tokens_to_ids(target_code),
                max_new_tokens=400,
                num_beams=4,
                repetition_penalty=1.1,
            )
            decoded = tokenizer.batch_decode(translated, skip_special_tokens=True)
            for (idx, _), text in zip(items, decoded):
                results[idx] = text.strip() if text else None
        except Exception as e:
            log.error(f"[nllb] Batch translation failed ({src_code}→mk): {e}")

    return results


def is_available() -> bool:
    """Check if the NLLB model can be loaded."""
    model, _ = _load_model()
    return model is not None
