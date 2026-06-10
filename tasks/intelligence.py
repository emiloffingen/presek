from core.api_helpers import normalize_citation_sources, normalize_perspectives, normalize_summary_text
from core.entities import extract_entities, validate_person_names
from core.prompts import (
    SUMMARY_SYSTEM_PROMPT_MK,
    SUMMARY_SYSTEM_PROMPT_SR,
    SYNTHESIS_SYSTEM_PROMPT_MK,
    SYNTHESIS_SYSTEM_PROMPT_SR,
)
from core.text_extraction import clean_extracted_article_text
from nlp.categories import normalize_headline
from nlp import (
    deShout,
    extract_cluster_tags_locally,
    filter_cluster_tags,
    generate_local_placeholder,
    summarize_article_fallback,
    synthesize_cluster_fallback,
)
from nlp.categories import detect_category, detect_topic
from nlp.local_analyst import analyst
from tasks.utils import (
    get_celery_queue_depth,
    invalidate_cluster_caches,
    invalidate_public_data_caches,
    log,
    record_runtime_event,
    redis_client,
    schedule_task_once,
)
from utils import get_dominant_color

SUPPORTED_LANGS = ["sr", "mk"]
COUNTRY_LANG = {"RS": "sr", "MK": "mk"}

STRONG_IMAGE_SQL_FILTER = """
    image_url IS NOT NULL
    AND image_url NOT LIKE '%%placeholder%%'
    AND image_url NOT LIKE '%%default%%'
    AND image_url NOT LIKE '%%.svg'
    AND image_url NOT LIKE '%%logo%%'
    AND image_url NOT LIKE '%%emblem%%'
    AND image_url NOT LIKE '%%avatar%%'
    AND image_url NOT LIKE '%%icon%%'
    AND image_url NOT LIKE '%%favicon%%'
    AND image_url NOT LIKE '%%sprite%%'
    AND image_url NOT LIKE '%%banner%%'
    AND image_url NOT LIKE '%%social%%'
    AND image_url NOT LIKE '%%fallback%%'
    AND image_url NOT LIKE '%%no-image%%'
"""
import datetime
import json
import os
import re
import sys
import threading

from core.ai_engine import clean_json_response, generate_cover_art
from core.ai_engine import sync_call_ai as _call_ai
from core.celery_app import celery_app
from core.config import CLUSTER_LOOKBACK
from core.database import db_manager as db
from core.embeddings import average_embeddings, parse_embedding_value

_analyst_semaphore = threading.Semaphore(2)
_BACKFILL_QUEUE_DEPTH_LIMIT = 100
_BACKFILL_BATCH_SIZE = int(os.environ.get("BACKFILL_CLUSTERS_PER_RUN", "8"))
_METADATA_BATCH_SIZE = int(os.environ.get("CLUSTER_METADATA_BATCH_SIZE", "25"))
_ARTICLE_BATCH_SIZE = int(os.environ.get("ARTICLE_BATCH_SIZE", "20"))


def _queue_backlog_high(limit=_BACKFILL_QUEUE_DEPTH_LIMIT) -> bool:
    return get_celery_queue_depth() >= limit


def _dispatch_batched(task, ids, batch_size=_ARTICLE_BATCH_SIZE):
    if not ids:
        return
    for start in range(0, len(ids), batch_size):
        task.delay(ids[start : start + batch_size])

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@celery_app.task
def summarize_articles_batch_task(article_ids):
    """Batch processes AI summarization for articles."""
    for article_id in article_ids:
        summarize_article_task(article_id)


@celery_app.task
def detect_global_stories_batch_task(article_ids):
    """Batch processes global story detection for articles."""
    for article_id in article_ids:
        detect_global_story_task(article_id)


@celery_app.task
def standardize_article_styles_batch_task(article_ids):
    """Batch processes style standardization for articles."""
    for article_id in article_ids:
        standardize_article_style_task(article_id)


@celery_app.task(rate_limit="50/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def summarize_article_task(article_id, final_title=None):
    """Refines article content using AI summarization."""
    row = db.execute_one(
        "SELECT title, description, full_content, topic, category FROM articles WHERE id = %s",
        (article_id,),
    )
    if not row:
        return

    title = final_title or row.get("title")
    description = row.get("description", "")
    full_content = row.get("full_content", "")
    topic = row.get("topic")

    context_text = full_content if len(full_content or "") > len(description or "") else description

    # AI summarization logic
    prompt_parts = [f"Naslov: {str(title or '').strip()}"]
    if context_text:
        prompt_parts.append(
            f"Tekst za rezimiranje:\n<article_content>\n{
                str(context_text).strip()[
                    :10000]}\n</article_content>"
        )
    prompt = "\n".join(part for part in prompt_parts if part)

    # Determine which prompt to use based on existing category or topic if possible,
    # but default to Serbian as the primary processing language for now.
    # In a full multi-lang setup, we'd summarize in the language of the source.
    from core.language import detect_language

    lang = detect_language(title + " " + (description or ""))
    system_prompt = SUMMARY_SYSTEM_PROMPT_MK if lang == "mk" else SUMMARY_SYSTEM_PROMPT_SR

    raw_output, provider = _call_ai(
        prompt,
        system_prompt,
        task_type="summarize",
        topic=topic,
        json_mode=False,
        lang=lang,
    )

    final_text = None
    if raw_output:
        parsed = clean_json_response(raw_output)
        if isinstance(parsed, dict) and "summary" in parsed:
            final_text = parsed["summary"]
        else:
            final_text = re.sub(r"^```(json)?\s*", "", raw_output.strip())
            final_text = re.sub(r"\s*```$", "", final_text)

    if final_text:
        final_text = validate_person_names(final_text)
        db.execute(
            "UPDATE articles SET summary = %s WHERE id = %s",
            (final_text, article_id),
            fetch=False,
        )
        invalidate_public_data_caches()
        log.info(f"Successfully summarized article {article_id}")
    else:
        fallback = summarize_article_fallback(title, context_text, topic=topic, lang=lang)
        if fallback:
            db.execute(
                "UPDATE articles SET summary = %s WHERE id = %s",
                (fallback, article_id),
                fetch=False,
            )
            invalidate_public_data_caches()


def _load_cluster_articles_for_synthesis(cluster_id):
    return db.execute(
        "SELECT title, description, summary, full_content, source, link, created_at, category, topic, country, embedding FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )


def _langs_for_cluster_articles(article_rows):
    countries = {
        str(row.get("country") or "").upper()
        for row in (article_rows or [])
        if str(row.get("country") or "").strip()
    }
    langs = [COUNTRY_LANG[country] for country in ("RS", "MK") if country in countries]
    return langs or ["sr"]


def _build_cluster_synthesis_content(article_rows):
    rows = article_rows or []
    return "\n".join(
        f"- [{row.get('source') or 'izvor'}]: {row.get('title') or ''}" for row in rows[:10] if row.get("title")
    )


def _build_cluster_synthesis_prompt(article_rows, lang="sr", history_context="", legacy_summary=""):
    rows = article_rows or []
    prompt_parts = []
    if history_context:
        prompt_parts.append(history_context)
    prompt_parts.append("novi clanci OD danas:\n<articles_context>")

    context_lines = []
    for idx, article in enumerate(rows[:8], 1):
        content = article.get("full_content") or article.get("summary") or article.get("description") or ""
        context_lines.append(
            "\n".join(
                [
                    f"[{idx}] Source: {article.get('source') or 'unknown'}",
                    f"Title: {article.get('title') or ''}",
                    f"Description: {article.get('description') or ''}",
                    f"Content: {str(content)[:2200]}",
                ]
            )
        )

    prompt_parts.append("\n---\n".join(context_lines) or _build_cluster_synthesis_content(rows))
    if legacy_summary:
        prompt_parts.append(f"Prethodni sazetak kao kontekst:\n{legacy_summary}")
    prompt_parts.append("</articles_context>")

    if lang == "mk":
        prompt_parts.append(
            "УРЕДНИЧКИ ФОКУС: резимето не смее да биде список на наслови. "
            "Изведи 3-4 паметни точки: нов развој, зошто е важен, што навистина е потврдено "
            "и што останува непознато или следно за проверка."
        )
    else:
        prompt_parts.append(
            "UREĐIVAČKI FOKUS: rezime ne sme biti lista naslova. "
            "Izvedi 3-4 pametne tačke: novi razvoj, zašto je važan, šta je zaista potvrđeno "
            "i šta ostaje nepoznato ili sledeće za proveru."
        )
    return "\n\n".join(part for part in prompt_parts if part)


def _resolve_generation_model(provider: str | None):
    if not provider:
        return None
    from core.ai_engine import PROVIDERS

    provider_obj = PROVIDERS.get(provider)
    if provider_obj and getattr(provider_obj, "model", None):
        return provider_obj.model
    return provider


def _generate_synthesis_via_cascade(
    article_rows,
    full_prompt,
    system_prompt,
    lang="sr",
    max_tokens=3000,
    fast_mode=False,
    current_context=None,
    legacy_summary=None,
):
    """Run router-directed provider cascade with JSON, grounding, and quality gates."""
    from core.ai_engine import build_provider_fallback_order
    from core.llm_router import SmartModelRouter

    if not article_rows:
        return {
            "status": "deterministic",
            "provider": "enhanced_fallback",
            "model": "enhanced_fallback",
            "fallback_reason": "router_empty_articles",
            "res_data": None,
            "quality_score": None,
            "raw": None,
        }

    primary_provider = SmartModelRouter.route_cluster(article_rows, lang=lang)
    if primary_provider == "enhanced_fallback":
        return {
            "status": "deterministic",
            "provider": "enhanced_fallback",
            "model": "enhanced_fallback",
            "fallback_reason": "router_selected_fallback",
            "res_data": None,
            "quality_score": None,
            "raw": None,
        }

    exclude_providers: list[str] = []
    last_fallback_reason = None
    max_attempts = len(build_provider_fallback_order("synthesis", primary_provider))

    while len(exclude_providers) < max_attempts:
        raw, provider = _call_ai(
            full_prompt,
            system_prompt,
            json_mode=True,
            task_type="synthesis",
            max_tokens=max_tokens,
            lang=lang,
            provider_override=primary_provider,
            exclude_providers=exclude_providers,
        )
        if not raw or not provider:
            last_fallback_reason = last_fallback_reason or "provider_returned_no_content"
            break

        try:
            res_data = clean_json_response(raw)
            if not isinstance(res_data, dict):
                raise ValueError("Parsed JSON is not a dictionary")
        except Exception as exc:
            log.error(f"[tasks/synthesis] JSON parse error from {provider}: {exc}")
            last_fallback_reason = "malformed_json"
            exclude_providers.append(provider)
            continue

        summary = res_data.get("summary", "")
        generated_article = res_data.get("article", "") or res_data.get("generated_article", "")
        synthetic_headline = res_data.get("synthetic_headline", "")
        if isinstance(summary, list):
            summary = "\n".join(str(s) for s in summary)

        if not summary or not generated_article:
            last_fallback_reason = "partial_response"
            exclude_providers.append(provider)
            continue

        comparison_text = f"{summary}\n{generated_article}"
        if not fast_mode and not _is_grounded_synthesis(comparison_text, current_context or legacy_summary):
            log.warning(f"[tasks/synthesis] Hallucination gate failed for provider {provider}")
            last_fallback_reason = "hallucination_gate_failed"
            exclude_providers.append(provider)
            continue

        key_facts = res_data.get("key_facts", [])
        article_score = _score_synthesis_quality(synthetic_headline, generated_article, key_facts, lang)
        summary_score = _score_editorial_summary(summary, generated_article, lang)
        quality_score = round((article_score * 0.65) + (summary_score * 0.35), 3)
        if not fast_mode and quality_score < 0.7:
            log.warning(
                f"[tasks/synthesis] Quality score {quality_score:.2f} below threshold for provider {provider}"
            )
            last_fallback_reason = "failed_quality_score"
            exclude_providers.append(provider)
            continue

        return {
            "status": "success",
            "provider": provider,
            "model": _resolve_generation_model(provider),
            "fallback_reason": None,
            "res_data": res_data,
            "quality_score": quality_score,
            "raw": raw,
        }

    return {
        "status": "exhausted",
        "provider": None,
        "model": None,
        "fallback_reason": last_fallback_reason or "cascade_exhausted",
        "res_data": None,
        "quality_score": None,
        "raw": None,
    }


def _normalize_cluster_synthesis(summary, perspectives, article_rows, lang="mk"):
    clean_summary = normalize_summary_text(summary)
    clean_perspectives = normalize_perspectives(perspectives)

    if clean_summary and clean_perspectives:
        return clean_summary, clean_perspectives

    fallback = synthesize_cluster_fallback(article_rows, lang=lang)
    fallback_summary = normalize_summary_text(fallback.get("summary", ""))
    fallback_perspectives = normalize_perspectives(fallback.get("perspectives", []))

    if not clean_summary:
        clean_summary = fallback_summary
    if not clean_perspectives:
        clean_perspectives = fallback_perspectives

    return clean_summary, clean_perspectives


def _looks_like_leaked_json_fragment(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    lowered = clean.lower()
    json_markers = (
        '"synthetic_headline"',
        '"synthetic_standfirst"',
        '"summary"',
        '"generated_article"',
        '"key_facts"',
        '"perspectives"',
        "verification_report",
    )
    marker_count = sum(1 for marker in json_markers if marker in lowered)
    bullet_json_lines = sum(1 for line in clean.splitlines() if line.strip().startswith(("• {", "• \"", "{", "\"")))
    return marker_count >= 2 or bullet_json_lines >= 2


def _paragraph_fingerprint(text: str) -> str:
    return re.sub(r"\W+", " ", str(text or "").casefold()).strip()


def _dedupe_generated_article(text: str) -> str:
    parts = [part.strip() for part in re.split(r"\n{2,}", str(text or "")) if part.strip()]
    kept = []
    seen = set()
    for part in parts:
        key = _paragraph_fingerprint(part)
        if not key or key in seen:
            continue
        if any(key and (key in prev or prev in key) and min(len(key), len(prev)) > 120 for prev in seen):
            continue
        seen.add(key)
        kept.append(part)
    return "\n\n".join(kept).strip()


def _polish_generated_article(text: str, lang: str = "mk") -> str:
    clean = str(text or "").strip()
    if not clean:
        return ""

    heading_patterns = (
        r"^\s*(синтеза|уреднички преглед|уредничка синтеза|анализа|article)\s*:?\s*$",
        r"^\s*(sinteza|urednički pregled|urednicki pregled|urednička sinteza|urednicka sinteza|analiza|article)\s*:?\s*$",
    )
    meta_leads = (
        (r"^\s*Овој кластер(?:\s+вести)?\s+", ""),
        (r"^\s*Оваа синтеза\s+", ""),
        (r"^\s*Според медиумските извештаи,\s*", ""),
        (r"^\s*Во вестите се наведува дека\s+", ""),
        (r"^\s*Ovaj klaster(?:\s+vesti)?\s+", ""),
        (r"^\s*Ova sinteza\s+", ""),
        (r"^\s*Prema medijskim izveštajima,\s*", ""),
        (r"^\s*U vestima se navodi da\s+", ""),
    )

    polished_parts = []
    for part in re.split(r"\n{2,}", clean):
        paragraph = re.sub(r"\s+", " ", part).strip()
        if not paragraph:
            continue
        if any(re.match(pattern, paragraph, flags=re.IGNORECASE) for pattern in heading_patterns):
            continue
        for pattern, replacement in meta_leads:
            paragraph = re.sub(pattern, replacement, paragraph, flags=re.IGNORECASE).strip()
        if paragraph:
            polished_parts.append(paragraph)

    return "\n\n".join(polished_parts).strip()


def _clean_macedonian_spelling_and_script(text: str) -> str:
    if not text:
        return text

    # Direct homoglyph map (lookalikes swap) for mixed words
    homoglyphs = {
        'a': 'а', 'c': 'ц', 'e': 'е', 'o': 'о', 'p': 'п', 'x': 'х', 'y': 'у',
        'j': 'ј', 's': 'с', 'i': 'и',
        'A': 'А', 'C': 'Ц', 'E': 'Е', 'O': 'О', 'P': 'П', 'X': 'Х', 'Y': 'У',
        'J': 'Ј', 'S': 'С', 'I': 'И', 'K': 'К', 'M': 'М', 'T': 'Т', 'B': 'В',
        'H': 'Н', 'R': 'Р'
    }

    # Serbian to Macedonian leak mappings (both Cyrillic and Latin versions)
    # We will do case-insensitive word replacements
    leaks = {
        "током": "во текот на",
        "између": "меѓу",
        "измеѓу": "меѓу",
        "такође": "исто така",
        "како би": "за да",
        "да ли": "дали",
        "нису": "не се",
        "јесте": "е",
        "председник": "претседател",
        "премијер": "премиер",
        "министар": "министер",
        "саопштење": "соопштение",
        "тужилаштво": "обвинителство",
        "оптужница": "обвинение",
        "сарадња": "соработка",
        "састанак": "состанок",
        "земља": "земја",
        "недеља": "недела",
        "понедељак": "понеделник",
        "уторак": "вторник",
        "четвртак": "четврток",
        "петак": "петок",
        "субота": "сабота",
        "јануар": "јануари",
        "фебруар": "февруари",
        "октобар": "октомври",
        "новембар": "ноември",
        "децембар": "декември",
        "догађај": "настан",
        "због": "поради",
        "учешће": "учество",
        "предузеће": "претпријатие",
        "грађани": "граѓани",
        "грађанин": "граѓанин",
        "држављанин": "државјанин",
        "држављани": "државјани",
        "унутрашњи": "внатрешен",
        "спољашњи": "надворешен",
        "избеглице": "бегалци",
        "ухапшен": "уапсен",
        "ухапшени": "уапсени",
        "помоћ": "помош",
        "савез": "сојуз",
        "захтев": "барање",
        "веза": "врска",
        "избор": "избор",
        "избори": "избори",
        "решење": "решение",
        "односи": "односи",
        "већ": "веќе",
        
        # Latin leaks
        "tokom": "во текот на",
        "između": "меѓу",
        "takođe": "исто така",
        "kako bi": "за да",
        "da li": "дали",
        "nisu": "не се",
        "jeste": "е",
        "predsednik": "претседател",
        "premijer": "премиер",
        "ministar": "министер",
        "saopštenje": "соопштение",
        "tužilaštvo": "обвинителство",
        "optužnica": "обвинение",
        "saradnja": "соработка",
        "sastanak": "состанок",
        "zemlja": "земја",
        "nedelja": "недела",
        "ponedeljak": "понеделник",
        "utorak": "вторник",
        "četvrtak": "четврток",
        "petak": "петок",
        "subota": "сабота",
        "januar": "јануари",
        "februar": "февруари",
        "oktobar": "октомври",
        "novembar": "ноември",
        "decembar": "декември",
        "događaj": "настан",
        "zbog": "поради",
        "učešće": "учество",
        "preduzeće": "претпријатие",
        "građani": "граѓани",
        "građanin": "граѓанин",
        "državljanin": "државјанин",
        "državljani": "државјани",
        "unutrašnji": "внатрешен",
        "spoljašnji": "надворешен",
        "izbeglice": "бегалци",
        "uhapšen": "уапсен",
        "uhapšeni": "уапсени",
        "pomoć": "помош",
        "savez": "сојуз",
        "zahtev": "барање",
        "već": "веќе",
    }

    # Helper for full Latin phonetic transliteration
    phonetic = {
        "Lj": "Љ", "lj": "љ",
        "Nj": "Њ", "nj": "њ",
        "Dž": "Џ", "dž": "џ",
        "Gj": "Ѓ", "gj": "ѓ",
        "Kj": "Ќ", "kj": "ќ",
        "Dz": "Ѕ", "dz": "ѕ",
        "A": "А", "a": "а",
        "B": "Б", "b": "б",
        "V": "В", "v": "в",
        "G": "Г", "g": "г",
        "D": "Д", "d": "д",
        "Đ": "Ѓ", "đ": "ѓ",
        "E": "Е", "e": "е",
        "Ž": "Ж", "ž": "ж",
        "Z": "З", "z": "з",
        "I": "И", "i": "и",
        "J": "Ј", "j": "ј",
        "K": "К", "k": "к",
        "L": "Л", "l": "л",
        "M": "М", "m": "м",
        "N": "Н", "n": "н",
        "O": "О", "o": "о",
        "P": "П", "p": "п",
        "R": "Р", "r": "р",
        "S": "С", "s": "с",
        "T": "Т", "t": "т",
        "Ć": "Ќ", "ć": "ќ",
        "U": "У", "u": "у",
        "F": "Ф", "f": "ф",
        "H": "Х", "h": "х",
        "C": "Ц", "c": "ц",
        "Č": "Ч", "č": "ч",
        "Š": "Ш", "š": "ш",
    }

    def clean_word(word: str) -> str:
        if word.startswith('[') and word.endswith(']'):
            return word
        
        w_lower = word.lower()
        if w_lower in leaks:
            replacement = leaks[w_lower]
            if word[0].isupper():
                replacement = replacement[0].upper() + replacement[1:]
            return replacement

        has_cyrillic = any('\u0400' <= char <= '\u04FF' for char in word)
        has_latin = any(('a' <= char.lower() <= 'z') for char in word)
        
        if has_cyrillic and has_latin:
            chars = []
            for c in word:
                if c in homoglyphs:
                    chars.append(homoglyphs[c])
                else:
                    chars.append(c)
            return "".join(chars)

        if has_latin and not has_cyrillic:
            if word.isupper() and len(word) in (2, 3, 4, 5):
                return word
            
            res = word
            for lat, cyr in sorted(phonetic.items(), key=lambda x: len(x[0]), reverse=True):
                res = res.replace(lat, cyr)
            return res

        return word

    tokens = re.split(r'(\s+|[.,!?;:()""\'\'„“»«\[\]]+)', text)
    cleaned_tokens = []
    for token in tokens:
        if not token:
            continue
        if re.match(r'^[a-zA-Z\u0400-\u04FF\u0160\u0161\u0106\u0107\u010C\u010D\u0110\u0111\u017D\u017E]+$', token):
            cleaned_tokens.append(clean_word(token))
        else:
            cleaned_tokens.append(token)

    return "".join(cleaned_tokens)


def _score_synthesis_quality(headline: str, article: str, key_facts: list, lang: str = "sr") -> float:
    """
    Evaluates synthesis quality, returning a score between 0.0 and 1.0.
    Docks points for repetition, poor citation/fact density, and broken paragraph structure.
    """
    score = 1.0
    if not headline or not article:
        return 0.0

    # 1. Headline repetition in body
    h_clean = headline.lower().strip()
    a_clean = article.lower().strip()
    if h_clean in a_clean:
        score -= 0.4

    # 2. Source-grounded facts/citations density
    citations = re.findall(r'\[\d+\]', article)
    facts_count = len(key_facts) if isinstance(key_facts, list) else 0
    if len(citations) < 4 and facts_count < 4:
        score -= 0.3

    # 3. Paragraph structure check (strictly 5 paragraphs)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', article) if p.strip()]
    if len(paragraphs) != 5:
        score -= 0.3

    return max(0.0, min(1.0, score))


_EDITORIAL_VAGUE_PATTERNS = (
    r"\brazvoj događaja\b",
    r"\bsituacija (?:je |ostaje )?dinamična\b",
    r"\bizvori izveštavaju\b",
    r"\bprivukao je pažnju\b",
    r"\bostaje da se vidi\b",
    r"\bširi kontekst\b",
    r"\bmedijski izvori\b",
    r"\bразвојот на настаните\b",
    r"\bситуацијата (?:е |останува )?динамична\b",
    r"\bизворите известуваат\b",
    r"\bпривлече внимание\b",
    r"\bостанува да се види\b",
    r"\bпоширок контекст\b",
    r"\bмедиумски извори\b",
)


def _split_summary_items(summary) -> list[str]:
    if isinstance(summary, list):
        raw_items = summary
    else:
        raw_items = str(summary or "").splitlines()

    items = []
    for item in raw_items:
        clean = re.sub(r"^[\s\-•*\d.)]+", "", str(item or "")).strip()
        clean = re.sub(r"^(šta se desilo|što se slučilo|што се случи|značaj|значење|otvoreno|отворено)\s*:\s*", "", clean, flags=re.IGNORECASE)
        if clean:
            items.append(clean)
    return items


def _score_editorial_summary(summary, article: str = "", lang: str = "sr") -> float:
    """
    Scores whether synthesis bullets read like editorial judgement rather than
    generic extraction. The target is 3-4 differentiated bullets: development,
    significance, source agreement/difference, and uncertainty/next signal.
    """
    items = _split_summary_items(summary)
    if not items:
        return 0.0

    score = 1.0
    if len(items) < 3:
        score -= 0.35
    if len(items) > 4:
        score -= 0.15

    all_text = " ".join(items)
    lowered = all_text.casefold()
    item_terms = []
    for item in items:
        words = set(re.findall(r"[A-Za-zÀ-žА-џ0-9]{4,}", item.casefold()))
        item_terms.append(words)

    # Repetition check: bullets should not be paraphrases of the same headline.
    for idx, current in enumerate(item_terms):
        for previous in item_terms[:idx]:
            if not current or not previous:
                continue
            overlap = len(current & previous) / max(1, min(len(current), len(previous)))
            if overlap > 0.72:
                score -= 0.18
                break

    vague_hits = sum(1 for pattern in _EDITORIAL_VAGUE_PATTERNS if re.search(pattern, lowered, flags=re.IGNORECASE))
    score -= min(0.3, vague_hits * 0.1)

    significance_markers = (
        "zato", "jer", "znač", "posled", "utic", "rizik", "ulog", "instituc", "budžet", "bezbed",
        "поради", "затоа", "знач", "послед", "влија", "ризик", "влог", "институц", "буџет", "безбед",
    )
    verification_markers = (
        "potvr", "saglas", "razlik", "nejas", "nepotvr", "otvoren", "izvor", "naredn", "sledeć",
        "потврд", "соглас", "разлик", "нејас", "непотврд", "отворен", "извор", "следн",
    )
    if not any(marker in lowered for marker in significance_markers):
        score -= 0.2
    if not any(marker in lowered for marker in verification_markers):
        score -= 0.2

    # Avoid summary bullets that simply duplicate article opening sentences.
    article_start = _paragraph_fingerprint(" ".join(str(article or "").split()[:80]))
    duplicate_bullets = 0
    for item in items:
        item_key = _paragraph_fingerprint(item)
        if item_key and len(item_key) > 50 and item_key in article_start:
            duplicate_bullets += 1
    score -= min(0.2, duplicate_bullets * 0.1)

    return max(0.0, min(1.0, score))


def _sanitize_synthesis_outputs(summary, generated_article, perspectives, article_rows, lang="mk"):
    fallback = None
    clean_summary = normalize_summary_text(summary)
    clean_article = _polish_generated_article(
        _dedupe_generated_article(validate_person_names(generated_article or "")),
        lang=lang,
    )

    if _looks_like_leaked_json_fragment(clean_summary):
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_summary = normalize_summary_text(fallback.get("summary", ""))

    if _looks_like_leaked_json_fragment(clean_article) or len(clean_article) < 80:
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_article = _polish_generated_article(
            _dedupe_generated_article(fallback.get("generated_article", "")),
            lang=lang,
        )

    clean_perspectives = normalize_perspectives(perspectives, lang=lang)
    if not clean_perspectives:
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_perspectives = normalize_perspectives(fallback.get("perspectives", []), lang=lang)

    # Strictly verify Cyrillic script and clean spelling leaks for Macedonian
    if lang == "mk":
        if isinstance(clean_summary, str):
            clean_summary = _clean_macedonian_spelling_and_script(clean_summary)
        elif isinstance(clean_summary, list):
            clean_summary = [_clean_macedonian_spelling_and_script(s) for s in clean_summary]
        
        clean_article = _clean_macedonian_spelling_and_script(clean_article)
        
        if isinstance(clean_perspectives, list):
            for p in clean_perspectives:
                if isinstance(p, dict):
                    if "angle" in p:
                        p["angle"] = _clean_macedonian_spelling_and_script(p["angle"])
                    if "content" in p:
                        p["content"] = _clean_macedonian_spelling_and_script(p["content"])

    return clean_summary, clean_article, clean_perspectives


def _ensure_dict(value):
    return value if isinstance(value, dict) else {}


def _fallback_key_facts(article_rows, summary="", limit=4):
    facts = []
    seen = set()

    for article in article_rows or []:
        source = str(article.get("source") or "izvor").strip()
        title = deShout(str(article.get("title") or "").strip())
        if not title:
            continue
        fact = f"{source}: {title}"
        key = fact.casefold()
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact[:220])
        if len(facts) >= limit:
            break
    return facts


def _build_citation_sources(article_rows):
    ordered = []
    for item in article_rows or []:
        ordered.append(
            {
                "source": str(item.get("source") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "link": str(item.get("link") or "").strip(),
                "created_at": str(item.get("created_at") or "").strip(),
                "category": str(item.get("category") or "").strip(),
            }
        )
    return normalize_citation_sources(ordered)


def _extract_one_quote_or_fact(text: str) -> str | None:
    if not text:
        return None
    # Look for quotes in text
    quote_patterns = [
        r'["“„»]([^"“„»]{15,})["”„«]',
        r'\'([^\']{15,})\''
    ]
    for pattern in quote_patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[0].strip()
    
    # If no quotes, find a sentence containing a number/fact
    sentences = re.split(r'[.!?]\s+', text)
    for s in sentences:
        if any(c.isdigit() for c in s) and len(s) > 20:
            return s.strip()
            
    # Default to the first sentence
    if sentences:
        first = sentences[0].strip()
        if len(first) > 10:
            return first
    return None


def _build_synthesis_source_context(article_rows, lang: str = "sr"):
    # Group and deduplicate by source, preserving order of first occurrence
    seen_sources = set()
    deduped_rows = []
    for row in (article_rows or []):
        source = str(row.get("source") or "").strip().lower()
        if source and source not in seen_sources:
            seen_sources.add(source)
            deduped_rows.append(row)
            
    # Feed only top 4-6 articles (we use 5)
    top_rows = deduped_rows[:5]
    
    blocks = []
    for idx, row in enumerate(top_rows, start=1):
        title = deShout(normalize_headline(str(row.get("title") or "").strip()))
        source = str(row.get("source") or "izvor").strip()
        created_at = str(row.get("created_at") or "").strip()
        category = str(row.get("category") or "").strip()
        topic = str(row.get("topic") or "").strip()
        description = clean_extracted_article_text(str(row.get("description") or "").strip())
        full_content = clean_extracted_article_text(str(row.get("full_content") or "").strip())
        
        evidence = full_content if len(full_content or "") > len(description or "") else description
        evidence = evidence[:1600].strip()
        
        extracted_fact = _extract_one_quote_or_fact(full_content or description)
        
        parts = [f"[{idx}] {source}"]
        if created_at:
            parts.append(f"{'Objavljeno' if lang == 'sr' else 'Објавено'}: {created_at}")
        if category:
            parts.append(f"{'Kategorija' if lang == 'sr' else 'Категорија'}: {category}")
        if topic:
            parts.append(f"{'Tema' if lang == 'sr' else 'Тема'}: {topic}")
        if title:
            parts.append(f"{'Naslov' if lang == 'sr' else 'Наслов'}: {title}")
        if evidence:
            parts.append(f"{'Opis' if lang == 'sr' else 'Опис'}:\n{evidence}")
        if extracted_fact:
            parts.append(f"{'Ključna izjava/činjenica' if lang == 'sr' else 'Клучна изјава/факт'}: {extracted_fact}")
            
        blocks.append("\n".join(parts))
        
    source_count = len(top_rows)
    if lang == "mk":
        header = (
            f"Достапни се {source_count} различни извори. Спореди ги по факти, акценти и пропусти; "
            "не претпоставувај мотиви и не користи податоци што не се во изворите."
        )
    else:
        header = (
            f"Dostupno je {source_count} različitih izvora. Uporedi ih po činjenicama, akcentima i propustima; "
            "ne pretpostavljaj motive i ne koristi podatke koji nisu u izvorima."
        )
    return f"{header}\n\n" + "\n\n".join(blocks) if blocks else ""


def _compute_centroid_from_values(values):
    return average_embeddings(values)


def _cosine_dist(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0


_GENERIC_CLUSTER_TOPICS = {"vesti", "news", ""}


def _cluster_text_similarity(left_titles, right_titles, lang="mk"):
    import core.clustering as clustering

    left_text = " ".join(str(title or "") for title in (left_titles or [])[:3])
    right_text = " ".join(str(title or "") for title in (right_titles or [])[:3])
    lexical = clustering.get_cosine(
        clustering.text_to_vector(left_text, lang=lang),
        clustering.text_to_vector(right_text, lang=lang),
    )
    phrase = 0.0
    for left in (left_titles or [])[:3]:
        for right in (right_titles or [])[:3]:
            phrase = max(phrase, clustering._title_phrase_overlap(str(left or ""), str(right or ""), lang=lang))
    return lexical, phrase


def _cluster_tag_set(row):
    return {str(tag or "").strip().lower() for tag in (row.get("tags") or []) if str(tag or "").strip()}


def _split_cluster_merge_score(left, right, lang="mk"):
    """Return a merge confidence for two already-created clusters, or 0 if unsafe."""
    if left.get("cluster_id") == right.get("cluster_id"):
        return 0.0
    if left.get("country") != right.get("country"):
        return 0.0
    if left.get("category") and right.get("category") and left.get("category") != right.get("category"):
        return 0.0

    left_topic = str(left.get("topic") or "").strip()
    right_topic = str(right.get("topic") or "").strip()
    if left_topic != right_topic:
        return 0.0

    left_latest = left.get("latest_article")
    right_latest = right.get("latest_article")
    if left_latest and right_latest:
        try:
            if abs((left_latest - right_latest).total_seconds()) > 36 * 3600:
                return 0.0
        except Exception:
            pass

    lexical, phrase = _cluster_text_similarity(left.get("titles"), right.get("titles"), lang=lang)
    shared_tags = _cluster_tag_set(left) & _cluster_tag_set(right)
    meaningful_shared_tags = {tag for tag in shared_tags if tag not in _GENERIC_CLUSTER_TOPICS}

    left_centroid = parse_embedding_value(left.get("centroid"))
    right_centroid = parse_embedding_value(right.get("centroid"))
    centroid_similarity = 0.0
    if left_centroid and right_centroid:
        centroid_similarity = 1 - _cosine_dist(left_centroid, right_centroid)

    generic_topic = left_topic.lower() in _GENERIC_CLUSTER_TOPICS
    if generic_topic:
        if len(meaningful_shared_tags) >= 2 and lexical >= 0.34:
            return round(lexical + phrase + len(meaningful_shared_tags) * 0.08 + centroid_similarity * 0.2, 4)
        if len(meaningful_shared_tags) >= 1 and lexical >= 0.28 and centroid_similarity >= 0.82:
            return round(lexical + phrase + centroid_similarity * 0.35, 4)
        return 0.0

    if lexical >= 0.42 or (phrase >= 0.25 and meaningful_shared_tags):
        return round(lexical + phrase + len(meaningful_shared_tags) * 0.06 + centroid_similarity * 0.15, 4)
    return 0.0


@celery_app.task(rate_limit="10/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def standardize_article_style_task(article_id):
    """Refines article linguistic style using the local style normalizer."""
    from core.config import ENABLE_EXPENSIVE_STYLE_TASKS

    if not ENABLE_EXPENSIVE_STYLE_TASKS:
        return

    row = db.execute_one(
        "SELECT title, description, topic, category, country FROM articles WHERE id = %s",
        (article_id,),
    )
    if not row:
        return

    title = row.get("title", "")
    topic = row.get("topic") or ""
    category = row.get("category") or ""
    country = row.get("country") or "MK"
    lang = "sr" if country == "SR" else "mk"

    if not title or len(title) < 25:
        return  # Skip very short headlines

    try:
        # Topic-Aware Bypass: Don't over-polish sports or entertainment as it kills the "vibe"
        if topic == "Sport" or category == "Sport":
            return

        # Use the local style normalizer for literary normalization.
        final_title = analyst.normalize_headline(title, lang=lang)

        if final_title and final_title.strip().lower() != title.strip().lower():
            # Check semantic similarity to ensure we didn't lose the plot
            from nlp.text_processing import _jaccard_similarity

            if _jaccard_similarity(title, final_title) < 0.35:
                log.warning(f"[style] Rejected over-aggressive polish for {article_id}")
                return

            # Preserve original for transparency/debugging
            db.execute(
                "UPDATE articles SET title = %s, original_title = %s, is_translated = 1 WHERE id = %s",
                (final_title, title, article_id),
                fetch=False,
            )
            log.info(f"[style] Standardized title for article {article_id} using local style normalizer")
            # Re-trigger summary if title changed significantly
            summarize_article_task.delay(article_id, final_title)

    except Exception as e:
        log.error(f"[style] Normalization failed for {article_id}: {e}")


@celery_app.task(rate_limit="15/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def detect_global_story_task(article_id):
    """Detects if a Macedonian article is a translation of a foreign global report."""
    from core.config import LOCAL_TRANSLATION_ENABLED

    if not LOCAL_TRANSLATION_ENABLED:
        return

    row = db.execute_one("SELECT title FROM articles WHERE id = %s", (article_id,))
    if not row or not row.get("title"):
        return

    try:
        import numpy as np

        from core.embeddings import generate_query_embedding
        from utils import redis_client

        # Use the multilingual embedding model (MiniLM-L12) to compare Macedonian
        # directly with global English headlines
        mk_vec = generate_query_embedding(row["title"])
        if not mk_vec:
            return

        # 3. Compare with Global Cache from Redis
        global_data = redis_client.get("presek:global_headlines:v1")
        if not global_data:
            return

        global_heads = json.loads(global_data)  # List of {"title": str, "vec": list}

        best_similarity = 0
        for head in global_heads:
            g_vec = np.array(head["vec"])
            sim = np.dot(mk_vec, g_vec) / (np.linalg.norm(mk_vec) * np.linalg.norm(g_vec))
            if sim > best_similarity:
                best_similarity = sim

        # 4. Verdict (0.82 is a strong semantic match for cross-lingual pairs)
        if best_similarity > 0.82:
            db.execute(
                "UPDATE articles SET is_global = TRUE WHERE id = %s",
                (article_id,),
                fetch=False,
            )
            log.info(
                f"[originality] Flagged article {
                     article_id} as GLOBAL (Sim: {best_similarity:.4f})"
            )

    except Exception as e:
        log.warning(f"[originality] Detection failed for {article_id}: {e}")


@celery_app.task(
    queue="fast-track",
    rate_limit="60/m",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def synthesize_urgent_task(cluster_id, content=None):
    """Priority synthesis for new clusters."""
    return synthesize_cluster_task(cluster_id, content, fast_mode=True)


@celery_app.task(rate_limit="60/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0, fast_mode=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    citation_sources = _build_citation_sources(article_rows)
    target_langs = _langs_for_cluster_articles(article_rows)
    source_context_sr = _build_synthesis_source_context(article_rows, lang="sr")
    source_context_mk = _build_synthesis_source_context(article_rows, lang="mk")

    # Non-fast synthesis needs room for a longer editorial article plus the surrounding JSON fields.
    max_tokens = 2200 if fast_mode else 5200

    # 1. Fetch Historical Context (Cross-Story Memory)
    # We'll fetch this once for the primary language (sr) to use as context for all syntheses
    history_context = ""
    try:
        from core.embeddings import get_cluster_embedding
        from core.config import HISTORY_SEMANTIC_THRESHOLD

        current_vec = get_cluster_embedding(cluster_id)
        if current_vec:
            current_vec_str = "[" + ",".join(map(str, current_vec)) + "]"
            # Find semantically similar clusters from the last 7 days (prefer Serbian for context)
            related = db.execute(
                """
                SELECT s.summary, s.generated_article, a.title
                FROM cluster_summaries s
                JOIN articles a ON s.cluster_id = a.cluster_id
                JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
                WHERE s.cluster_id != %s
                  AND s.lang = 'sr'
                  AND s.created_at >= NOW() - INTERVAL '7 days'
                  AND s.created_at < (SELECT MIN(created_at) FROM articles WHERE cluster_id = %s)
                  AND (m.centroid <=> %s::vector) < %s
                ORDER BY m.centroid <=> %s::vector
                LIMIT 1
            """,
                (cluster_id, cluster_id, current_vec_str, HISTORY_SEMANTIC_THRESHOLD, current_vec_str),
            )

            if related:
                r = related[0]
                prev_text = r["generated_article"] or r["summary"]
                if prev_text:
                    history_context = f"\nPRETHODEN kontekst (za ovoj nastan ili povrzana tema od izminatite denovi):\n<historical_context>\n{
                        prev_text[:1000]}\n</historical_context>"
    except Exception as e:
        log.warning(f"[tasks/memory] Failed to fetch history for {cluster_id}: {e}")

    legacy_summary = str(content or "").strip()

    # Track shared metrics that only need to be computed once per cluster
    shared_metrics = {
        "impact_score": 0.0,
        "impact_reasoning": "",
        "story_so_far": "",
        "centroid_str": None,
        "deep_metadata": {},
        "pluralism_data": {},
        "sentiment_data": {"sentiment": {"score": 0, "tone": "neutralan"}, "tone_analysis": {}},
        "citation_sources": citation_sources,
        "pulse_score": 50,
        "pluralism_score": 50,
        "analyst_entities": [],
    }
    shared_computed = False

    for lang in target_langs:
        try:
            log.info(f"Generating synthesis for cluster {cluster_id} in {lang}")
            prompt_parts = []
            if fast_mode:
                prompt_parts.append(
                    "FAST MODE: return the full valid JSON schema, but keep the editorial article concise and complete "
                    "(350-500 words). Include the core event, context, source comparison, consequences, and one clear "
                    "open question. Do not reduce the article to a single paragraph."
                )
            elif history_context:
                prompt_parts.append(history_context)

            prompt_parts.append("novi clanci OD danas:\n<articles_context>")
            current_context = source_context_mk if lang == "mk" else source_context_sr
            if current_context:
                prompt_parts.append(current_context)
            elif legacy_summary:
                prompt_parts.append(legacy_summary)
            prompt_parts.append("</articles_context>")
            if lang == "mk":
                prompt_parts.append(
                    "УРЕДНИЧКИ ФОКУС: резимето не смее да биде список на наслови. "
                    "Изведи 3-4 паметни точки: нов развој, зошто е важен, што навистина е потврдено "
                    "и што останува непознато или следно за проверка."
                )
            else:
                prompt_parts.append(
                    "UREĐIVAČKI FOKUS: rezime ne sme biti lista naslova. "
                    "Izvedi 3-4 pametne tačke: novi razvoj, zašto je važan, šta je zaista potvrđeno "
                    "i šta ostaje nepoznato ili sledeće za proveru."
                )
            full_prompt = "\n\n".join(part for part in prompt_parts if part)

            system_prompt = SYNTHESIS_SYSTEM_PROMPT_MK if lang == "mk" else SYNTHESIS_SYSTEM_PROMPT_SR

            cascade = _generate_synthesis_via_cascade(
                article_rows,
                full_prompt,
                system_prompt,
                lang=lang,
                max_tokens=max_tokens,
                fast_mode=fast_mode,
                current_context=current_context,
                legacy_summary=legacy_summary,
            )

            provider = cascade.get("provider")
            model = cascade.get("model")
            quality_score = cascade.get("quality_score")
            fallback_reason = cascade.get("fallback_reason")
            raw = cascade.get("raw")
            res_data = cascade.get("res_data") or {}

            if cascade["status"] == "success":
                summary = res_data.get("summary", "")
                generated_article = res_data.get("article", "") or res_data.get("generated_article", "")
                synthetic_headline = res_data.get("synthetic_headline", "")
                synthetic_standfirst = res_data.get("synthetic_standfirst", "")
                perspectives = res_data.get("perspectives", [])
                if isinstance(summary, list):
                    summary = "\n".join(str(s) for s in summary)

                verification_report = res_data.get("verification_report")
                quote = validate_person_names(res_data.get("quote", ""))

                # Sanitize for name hallucinations
                summary = validate_person_names(summary)
                generated_article = validate_person_names(generated_article)
                synthetic_headline = validate_person_names(synthetic_headline)
                synthetic_standfirst = validate_person_names(synthetic_standfirst)

                # --- [NEW] 2026 Intelligence: Storyline & Impact ---
                current_story_so_far = validate_person_names(res_data.get("story_so_far", ""))
                impact_data = _ensure_dict(res_data.get("impact_analysis", {}))
                current_impact_score = float(impact_data.get("score", 0.0))
                current_impact_reasoning = impact_data.get("reasoning", "")

                current_sentiment_data = {
                    "sentiment": res_data.get("sentiment", {}),
                    "tone_analysis": res_data.get("tone_analysis", {}),
                }

                summary, generated_article, perspectives = _sanitize_synthesis_outputs(
                    summary,
                    generated_article,
                    perspectives,
                    article_rows,
                    lang=lang,
                )
                record_runtime_event("synthesis_path", mode=provider or "unknown", fast_mode=fast_mode, lang=lang)
                
                # Record quality feedback for router
                if provider and not fast_mode and quality_score is not None:
                    from core.llm_router import SmartModelRouter

                    SmartModelRouter._record_quality_feedback(provider, cluster_id, quality_score)

                # Phase 3: Deep Local Analyst (SKIP in fast_mode)
                # Only run shared cluster-wide logic once (on first successful lang, usually sr)
                if not fast_mode and not shared_computed:

                    def _run_analyst_logic():
                        try:
                            # Use semaphore to limit concurrent heavy CPU tasks
                            with _analyst_semaphore:
                                # Run analyst on the current (first successful) summary
                                analyst_text = f"NASLOV: {synthetic_headline}\n{summary}"
                                shared_metrics["deep_metadata"] = analyst.extract_deep_metadata(analyst_text, lang=lang)

                                # Phase 3.1: Pluralism Assessment
                                titles_sources = [
                                    f"{a['source']}: {
                                    a['title']}"
                                    for a in article_rows[:10]
                                ]
                                shared_metrics["pluralism_data"] = analyst.assess_pluralism(titles_sources, lang=lang)

                                # Phase 3.2: Knowledge Graph Update
                                entities = shared_metrics["deep_metadata"].get("entities", [])
                                for entity in entities:
                                    with db.connection() as conn:
                                        with conn.cursor() as cur:
                                            try:
                                                cur.execute(
                                                    """
                                                    INSERT INTO knowledge_entities (name, type, last_seen, total_mentions)
                                                    VALUES (%s, 'PERSON', NOW(), 1)
                                                    ON CONFLICT (name) DO UPDATE SET
                                                        last_seen = NOW()
                                                """,
                                                    (entity,),
                                                )
                                                cur.execute(
                                                    """
                                                    INSERT INTO entity_mentions_daily (entity_name, cluster_id, day)
                                                    VALUES (%s, %s, CURRENT_DATE)
                                                    ON CONFLICT (entity_name, cluster_id, day) DO NOTHING
                                                """,
                                                    (entity, cluster_id),
                                                )
                                                cur.execute(
                                                    """
                                                    UPDATE knowledge_entities
                                                    SET total_mentions = (
                                                        SELECT COUNT(*) FROM entity_mentions_daily WHERE entity_name = %s
                                                    )
                                                    WHERE name = %s
                                                """,
                                                    (entity, entity),
                                                )
                                                conn.commit()
                                            except Exception as e:
                                                log.debug(f"Failed to update entity mentions: {e}")
                                                conn.rollback()
                                                raise
                        except Exception as e:
                            log.error(f"[analyst] Internal logic error: {e}")

                    analyst_thread = threading.Thread(target=_run_analyst_logic)
                    analyst_thread.start()
                    analyst_thread.join(timeout=600)  # 10 minute limit for low-core CPUs

                    if analyst_thread.is_alive():
                        log.warning(f"[analyst] Timeout reached for cluster {cluster_id}")

                    shared_metrics["deep_metadata"] = _ensure_dict(shared_metrics["deep_metadata"])
                    shared_metrics["pluralism_data"] = _ensure_dict(shared_metrics["pluralism_data"])

                    shared_metrics["impact_score"] = current_impact_score
                    shared_metrics["impact_reasoning"] = current_impact_reasoning
                    shared_metrics["story_so_far"] = current_story_so_far
                    shared_metrics["sentiment_data"] = current_sentiment_data

                    shared_metrics["pulse_score"] = shared_metrics["deep_metadata"].get("pulse", 50)
                    shared_metrics["pluralism_score"] = shared_metrics["pluralism_data"].get("score", 50)
                    shared_metrics["analyst_entities"] = shared_metrics["deep_metadata"].get("entities") or []

                    # Calculate Cluster Centroid (Semantic Center)
                    centroid = _compute_centroid_from_values(
                        [a.get("embedding") for a in article_rows if a.get("embedding")]
                    )
                    shared_metrics["centroid_str"] = (
                        f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None
                    )

                    shared_computed = True

            else:
                if cascade["status"] == "deterministic":
                    log.info(f"Using deterministic enhanced fallback for {cluster_id} ({lang})")
                else:
                    log.warning(
                        f"[tasks/synthesis] Provider cascade exhausted for {cluster_id} ({lang}); "
                        f"reason={fallback_reason}"
                    )
                provider = "enhanced_fallback"
                model = "enhanced_fallback"
                fallback_reason = fallback_reason or "enhanced_fallback_after_cascade_exhausted"
                fallback = synthesize_cluster_fallback(article_rows, lang=lang)
                summary = fallback.get("summary", "")
                perspectives = fallback.get("perspectives", [])
                synthetic_headline = fallback.get("synthetic_headline", "")
                synthetic_standfirst = fallback.get("synthetic_standfirst", "")
                generated_article = fallback.get("generated_article", "")
                record_runtime_event("synthesis_path", mode=provider, fast_mode=fast_mode, lang=lang)
                verification_report = None
                quote = ""
                current_sentiment_data = shared_metrics["sentiment_data"]

                if not shared_computed:
                    shared_metrics["impact_score"] = 0.0
                    shared_metrics["impact_reasoning"] = ""
                    shared_metrics["story_so_far"] = ""
                    shared_computed = True  # Mark as computed even if fallback

            summary, generated_article, perspectives = _sanitize_synthesis_outputs(
                summary,
                generated_article,
                perspectives,
                article_rows,
                lang=lang,
            )

            if summary or perspectives:
                # Use shared metrics for DB save
                pulse_score = shared_metrics["pulse_score"]
                pluralism_score = shared_metrics["pluralism_score"]
                pluralism_data = shared_metrics["pluralism_data"]
                if not pluralism_data:
                    pluralism_data = {
                        "score": pluralism_score,
                        "verdict": "Procenkata e vo tek." if lang == "mk" else "Procena je u toku.",
                    }

                key_facts = res_data.get("key_facts")
                if not key_facts or not isinstance(key_facts, list):
                    key_facts = shared_metrics["deep_metadata"].get("facts") or _fallback_key_facts(
                        article_rows, summary
                    )

                if lang == "mk" and key_facts:
                    # Translate Serbian Latin key facts to Macedonian Cyrillic
                    facts_text = "\n".join(f"- {f}" for f in key_facts)
                    translate_prompt = (
                        "Преведи ги следните клучни факти од српски (латиница) на чист македонски литературен јазик (кирилица).\n"
                        "Врати ги преведените факти како чист JSON од тип {\"facts\": [\"факт 1\", \"факт 2\", ...]} без никакви дополнителни објаснувања, markdown или воведи.\n\n"
                        f"{facts_text}"
                    )
                    try:
                        raw_trans, _ = _call_ai(
                            prompt=translate_prompt,
                            system="Ти си професионален преведувач за вести од српски на македонски јазик.",
                            task_type="translation",
                            max_tokens=500,
                            json_mode=True,
                            lang="mk"
                        )
                        if raw_trans:
                            trans_data = clean_json_response(raw_trans)
                            if isinstance(trans_data, dict) and trans_data.get("facts"):
                                translated_facts = trans_data["facts"]
                                if isinstance(translated_facts, list) and len(translated_facts) == len(key_facts):
                                    key_facts = translated_facts
                                    log.info("Successfully translated key_facts from Serbian to Macedonian")
                    except Exception as e:
                        log.warning(f"Failed to translate key_facts to Macedonian: {e}")

                # Archive current summary before updating (Evolution Log)
                db.execute(
                    """INSERT INTO cluster_summary_history (cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities, generation_provider, generation_model, quality_score, fallback_reason)
                       SELECT cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities, generation_provider, generation_model, quality_score, fallback_reason
                       FROM cluster_summaries WHERE cluster_id = %s AND lang = %s""",
                    (cluster_id, lang),
                    fetch=False,
                )

                if res_data.get("full_article_draft") and len(res_data["full_article_draft"]) > 100:
                    db.execute(
                        """INSERT INTO cluster_summaries (cluster_id, lang, summary, generated_article, synthetic_headline, synthetic_standfirst, created_at, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity, generation_provider, generation_model, quality_score, fallback_reason)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (cluster_id, lang) DO UPDATE SET
                               summary = EXCLUDED.summary,
                               generated_article = EXCLUDED.generated_article,
                               synthetic_headline = EXCLUDED.synthetic_headline,
                               synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                               created_at = EXCLUDED.created_at,
                               citation_sources = EXCLUDED.citation_sources,
                               key_facts = EXCLUDED.key_facts,
                               analyst_entities = EXCLUDED.analyst_entities,
                               pulse_score = EXCLUDED.pulse_score,
                               pluralism_score = EXCLUDED.pluralism_score,
                               narrative_diversity = EXCLUDED.narrative_diversity,
                               generation_provider = EXCLUDED.generation_provider,
                               generation_model = EXCLUDED.generation_model,
                               quality_score = EXCLUDED.quality_score,
                               fallback_reason = EXCLUDED.fallback_reason""",
                        (
                            cluster_id,
                            lang,
                            summary,
                            generated_article,
                            synthetic_headline,
                            synthetic_standfirst,
                            datetime.datetime.now(),
                            json.dumps(shared_metrics["citation_sources"]),
                            json.dumps(key_facts),
                            json.dumps(shared_metrics["analyst_entities"]),
                            float(pulse_score),
                            float(pluralism_score),
                            json.dumps(pluralism_data),
                            provider,
                            model,
                            quality_score,
                            fallback_reason,
                        ),
                        fetch=False,
                    )
                else:
                    db.execute(
                        """INSERT INTO cluster_summaries (cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, created_at, sentiment, tone_analysis, verification_report, quote, centroid, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity, storyline_narrative, generation_provider, generation_model, quality_score, fallback_reason)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (cluster_id, lang) DO UPDATE SET
                               summary = EXCLUDED.summary,
                               perspectives = EXCLUDED.perspectives,
                               generated_article = EXCLUDED.generated_article,
                               synthetic_headline = EXCLUDED.synthetic_headline,
                               synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                               created_at = EXCLUDED.created_at,
                               sentiment = EXCLUDED.sentiment,
                               tone_analysis = EXCLUDED.tone_analysis,
                               verification_report = EXCLUDED.verification_report,
                               quote = EXCLUDED.quote,
                               centroid = EXCLUDED.centroid,
                               citation_sources = EXCLUDED.citation_sources,
                               key_facts = EXCLUDED.key_facts,
                               analyst_entities = EXCLUDED.analyst_entities,
                               pulse_score = EXCLUDED.pulse_score,
                               pluralism_score = EXCLUDED.pluralism_score,
                               narrative_diversity = EXCLUDED.narrative_diversity,
                               storyline_narrative = EXCLUDED.storyline_narrative,
                               generation_provider = EXCLUDED.generation_provider,
                               generation_model = EXCLUDED.generation_model,
                               quality_score = EXCLUDED.quality_score,
                               fallback_reason = EXCLUDED.fallback_reason""",
                        (
                            cluster_id,
                            lang,
                            summary,
                            json.dumps(perspectives),
                            generated_article,
                            synthetic_headline,
                            synthetic_standfirst,
                            datetime.datetime.now(),
                            json.dumps(shared_metrics["sentiment_data"]),
                            json.dumps(res_data.get("tone_analysis", {})),
                            (json.dumps(verification_report) if verification_report else None),
                            quote,
                            shared_metrics["centroid_str"],
                            json.dumps(shared_metrics["citation_sources"]),
                            json.dumps(key_facts),
                            json.dumps(shared_metrics["analyst_entities"]),
                            float(pulse_score),
                            float(pluralism_score),
                            json.dumps(pluralism_data),
                            shared_metrics["story_so_far"],
                            provider,
                            model,
                            quality_score,
                            fallback_reason,
                        ),
                        fetch=False,
                    )
                log.info(f"Successfully synthesized cluster {cluster_id} for {lang}")

                # Automatically pre-generate the cluster audio in the background
                try:
                    from core.audio_service import AudioService
                    content = generated_article or summary
                    if content:
                        log.info(f"[tasks] Auto-generating cluster audio in background for cluster {cluster_id} ({lang})...")
                        AudioService.generate_cluster_audio(cluster_id, content, lang)
                except Exception as audio_err:
                    log.error(f"[tasks] Failed to auto-generate cluster audio for {cluster_id} ({lang}): {audio_err}")

        except Exception as e:
            log.error(f"Synthesis failed for cluster {cluster_id} in {lang}: {e}", exc_info=True)
            continue

    # --- [Final Steps] Cluster-wide updates and events ---
    if shared_computed:
        # Update Metadata with Impact Score
        db.execute(
            """
            UPDATE cluster_metadata
            SET impact_score = %s, impact_explanation = %s
            WHERE cluster_id = %s
        """,
            (shared_metrics["impact_score"], shared_metrics["impact_reasoning"], cluster_id),
            fetch=False,
        )

        # Publish SSE event
        try:
            from utils import publish_event

            is_breaking = False
            if article_rows:
                from core.config import BREAKING_SCORE_THRESHOLD
                from utils import score_cluster

                is_breaking = score_cluster(article_rows) >= BREAKING_SCORE_THRESHOLD

            publish_event(
                "updates",
                {
                    "type": "cluster_synthesis_updated",
                    "cluster_id": cluster_id,
                    "is_breaking": is_breaking,
                    "impact_score": shared_metrics["impact_score"],
                    "headline": article_rows[0].get("title", "") if article_rows else "",
                    "time": datetime.datetime.now().isoformat(),
                },
            )
        except Exception as pub_err:
            log.warning(f"[tasks] Failed to publish SSE event for {cluster_id}: {pub_err}")

        # Real-time Sports Score Alert (once)
        try:
            from nlp.categories import detect_topic

            all_titles = " ".join([a.get("title") or "" for a in article_rows])
            if detect_topic(all_titles) == "Sport":
                from notifier import BreakingNewsNotifier

                from core.config import NTFY_TOPIC
                from nlp.generation import _extract_sports_scores

                latest_scores = _extract_sports_scores(article_rows[0].get("title") or "") + _extract_sports_scores(
                    article_rows[0].get("description") or ""
                )
                if latest_scores:
                    latest_score = latest_scores[0]
                    notifier = BreakingNewsNotifier(NTFY_TOPIC)
                    notifier.notify_score_change(article_rows[0].get("title"), latest_score, cluster_id)
        except Exception as e:
            log.warning(f"[tasks/sports] Score alert failed: {e}")

        # Improved image logic: if no image or ONLY weak visuals exist, generate art
        strong_img = db.execute_one(
            f"SELECT 1 FROM articles WHERE cluster_id = %s AND {STRONG_IMAGE_SQL_FILTER} LIMIT 1",
            (cluster_id,),
        )
        if not strong_img:
            # We use first summary for placeholder generation (usually Serbian)
            summary_row = db.execute_one(
                "SELECT summary FROM cluster_summaries WHERE cluster_id = %s LIMIT 1", (cluster_id,)
            )
            if summary_row:
                svg_content = generate_local_placeholder(cluster_id, summary_row["summary"])
                img_url = generate_cover_art(cluster_id, svg_content)
                if img_url:
                    db.execute(
                        "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND (image_url IS NULL OR image_url LIKE '%%placeholder%%')",
                        (img_url, cluster_id),
                        fetch=False,
                    )

        try:
            invalidate_cluster_caches(cluster_id)
            if os.environ.get("REDIS_URL"):
                generate_cluster_metadata_task.apply_async(
                    kwargs={"target_clusters": [cluster_id]},
                    countdown=5,
                )
        except Exception as err:
            log.warning(f"[tasks] Finalization error for {cluster_id}: {err}")
    else:
        # Fallback if all languages failed
        log.error(f"All synthesis attempts failed for cluster {cluster_id}")


@celery_app.task
def auto_summarize_task(cluster_ids: list[str] = None):
    """Dispatch summarization/synthesis tasks for top clusters or targeted clusters."""
    from core.ai_engine import auto_summarize_top_clusters

    auto_summarize_top_clusters(target_cluster_ids=cluster_ids)


@celery_app.task
def refresh_cluster_centroid_task(cluster_id):
    """
    Recalculates and updates the semantic centroid for a cluster.
    """
    from core.database import db_manager as db
    from core.embeddings import get_cluster_embedding

    new_centroid = get_cluster_embedding(cluster_id)
    if new_centroid:
        vec_str = "[" + ",".join(map(str, new_centroid)) + "]"
        db.execute(
            "UPDATE cluster_metadata SET centroid = %s::vector WHERE cluster_id = %s",
            (vec_str, cluster_id),
            fetch=False,
        )
        log.info(f"[tasks] Centroid updated for cluster {cluster_id}")


@celery_app.task
def extract_entities_task(*args, hours=24, target_clusters=None, **kwargs):
    """Extract entities for top clusters using local hybrid logic (Lexicon + spaCy + Regex)."""
    try:
        if target_clusters:
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
                FROM articles WHERE cluster_id = ANY(%s) GROUP BY cluster_id
            """,
                (target_clusters,),
            )
        else:
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=int(hours or 24))
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
                FROM articles WHERE created_at >= %s GROUP BY cluster_id
                HAVING COUNT(DISTINCT source) >= 2 LIMIT 50
            """,
                (cutoff,),
            )

        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"

            # Use hybrid local extractor (curated lexicon + spaCy NER + regex)
            entities = extract_entities(text, max_entities=8)

            if entities:
                from core.entities import update_knowledge_graph

                # update_knowledge_graph calculates local sentiment automatically
                update_knowledge_graph(entities, context_text=text)

                for ent in entities:
                    db.execute(
                        "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (r["cluster_id"], ent.get("name"), ent.get("type")),
                        fetch=False,
                    )

        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("extract_entities", "ok", "clusters:recent:local")
    except Exception as e:
        log.error(f"[tasks] Local entity extraction failed: {e}")


@celery_app.task
def classify_topics_task(*args, **kwargs):
    """Classify default 'vesti' clusters using local rule-based detection."""
    try:
        # Increased limit as local classification is nearly free
        rows = db.execute("SELECT cluster_id, title FROM articles WHERE topic = 'vesti' LIMIT 200")
        for r in rows:
            topic = detect_topic(r["title"])
            if topic != "vesti":
                db.execute(
                    "UPDATE articles SET topic = %s WHERE cluster_id = %s",
                    (topic, r["cluster_id"]),
                    fetch=False,
                )
    except Exception as e:
        log.error(f"[tasks] Topic classification failed: {e}")
    else:
        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("classify_topics", "ok", "clusters:recent:local")


@celery_app.task
def recategorize_clusters_task(*args, **kwargs):
    """Verify if 'Srbija' articles belong in specialized categories using rule-based detection."""
    try:
        rows = db.execute("SELECT cluster_id, title, description FROM articles WHERE category = 'Srbija' LIMIT 20")
        for r in rows:
            # Rule-based first (Free)
            res = detect_category(r["title"], description=r.get("description", ""))
            if res != "Srbija":
                db.execute(
                    "UPDATE articles SET category = %s WHERE cluster_id = %s",
                    (res, r["cluster_id"]),
                    fetch=False,
                )
                continue
    except Exception as e:
        from tasks import utils

        utils.record_task_event("recategorize_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Recategorization failed: {e}")
    else:
        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("recategorize_clusters", "ok", "clusters:recent")


@celery_app.task
def generate_cluster_metadata_task(hours=24, target_clusters=None):
    """Tag recent clusters with metadata (entities, source count, centroid, and representative image)."""
    try:
        if _queue_backlog_high():
            log.info("[tasks] Skipping cluster metadata generation while queue backlog is high.")
            return

        if target_clusters:
            batch_ids = list(target_clusters)[:_METADATA_BATCH_SIZE]
            pending_ids = list(target_clusters)[_METADATA_BATCH_SIZE:]
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles,
                       array_agg(DISTINCT topic) as topics,
                       mode() WITHIN GROUP (ORDER BY category) as dominant_category,
                       array_agg(embedding) FILTER (WHERE embedding IS NOT NULL) as embeddings
                FROM articles WHERE cluster_id = ANY(%s)
                GROUP BY cluster_id
            """,
                (batch_ids,),
            )
            has_more = bool(pending_ids)
        else:
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=int(hours or 24))
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles,
                       array_agg(DISTINCT topic) as topics,
                       mode() WITHIN GROUP (ORDER BY category) as dominant_category,
                       array_agg(embedding) FILTER (WHERE embedding IS NOT NULL) as embeddings
                FROM articles WHERE created_at >= %s
                GROUP BY cluster_id
                ORDER BY MAX(created_at) DESC
                LIMIT %s
            """,
                (cutoff, _METADATA_BATCH_SIZE + 1),
            )
            has_more = len(rows) > _METADATA_BATCH_SIZE
            rows = rows[:_METADATA_BATCH_SIZE]
            pending_ids = None
        for r in rows:
            entities = db.execute(
                "SELECT entity_name, entity_type FROM cluster_entities WHERE cluster_id = %s",
                (r["cluster_id"],),
            )
            entity_candidates = [dict(e) for e in entities]
            final_tags = extract_cluster_tags_locally(
                titles=r["titles"],
                entity_names=entity_candidates,
                sources=r["sources"],
                top_n=8,
            )
            if not final_tags:
                final_tags = filter_cluster_tags(r["sources"], limit=4)

            # Calculate Centroid (Semantic Center)
            centroid = _compute_centroid_from_values(r.get("embeddings") or [])
            centroid_str = f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None

            # Smart image selection: prefer high-quality sources and non-placeholder URLs
            img_row = db.execute_one(
                """
                SELECT image_url, source
                FROM articles
                WHERE cluster_id = %s
                  AND image_url IS NOT NULL
                  AND image_url NOT LIKE '%%placeholder%%'
                  AND image_url NOT LIKE '%%default%%'
                  AND image_url NOT LIKE '%%.svg'
                  AND image_url NOT LIKE '%%logo%%'
                  AND image_url NOT LIKE '%%emblem%%'
                  AND image_url NOT LIKE '%%avatar%%'
                  AND image_url NOT LIKE '%%icon%%'
                  AND image_url NOT LIKE '%%favicon%%'
                  AND image_url NOT LIKE '%%sprite%%'
                  AND image_url NOT LIKE '%%banner%%'
                  AND image_url NOT LIKE '%%social%%'
                  AND image_url NOT LIKE '%%fallback%%'
                  AND image_url NOT LIKE '%%no-image%%'
                ORDER BY
                    (
                        CASE WHEN image_url ~* '(thumb|thumbnail|sprite|logo|icon|avatar|favicon|pixel|small|social)' THEN -15 ELSE 0 END +
                        CASE WHEN image_url ~* '(hero|lead|main|large|full|original)' THEN 5 ELSE 0 END +
                        CASE WHEN image_url ~* '\\.(avif|webp)(\\?|$)' THEN 4 ELSE 0 END +
                        CASE WHEN image_url ~* '\\.(jpe?g)(\\?|$)' THEN 3 ELSE 0 END +
                        CASE WHEN image_url ~* '\\.png(\\?|$)' THEN -2 ELSE 0 END +
                        CASE WHEN image_url ~* '(^|[^0-9])(1[2-9][0-9]{2}|[2-9][0-9]{3})x(1[2-9][0-9]{2}|[2-9][0-9]{3})([^0-9]|$)' THEN 6 ELSE 0 END +
                        CASE
                            WHEN source ILIKE '%%sdk%%' THEN 4
                            WHEN source ILIKE '%%360stepeni%%' THEN 4
                            WHEN source ILIKE '%%prizma%%' THEN 4
                            WHEN source ILIKE '%%sitel%%' THEN 2
                            WHEN source ILIKE '%%kanal5%%' THEN 2
                            WHEN source ILIKE '%%telma%%' THEN 3
                            WHEN source ILIKE '%%dw%%' THEN 4
                            ELSE 0
                        END
                    ) DESC,
                    created_at DESC
                LIMIT 1
            """,
                (r["cluster_id"],),
            )

            rep_image = img_row["image_url"] if img_row else None

            if not rep_image:
                # If we still have no image, try to generate one (AI cover art)
                svg_content = generate_local_placeholder(r["cluster_id"], r["titles"][0] if r["titles"] else "vest")
                rep_image = generate_cover_art(r["cluster_id"], svg_content)

            curr_meta = db.execute_one(
                "SELECT representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = %s",
                (r["cluster_id"],),
            )
            dominant_color = curr_meta["dominant_color"] if curr_meta else None

            if rep_image and (not curr_meta or curr_meta["representative_image"] != rep_image or not dominant_color):
                import asyncio

                dominant_color = asyncio.run(get_dominant_color(rep_image))

            db.execute(
                """INSERT INTO cluster_metadata (cluster_id, tags, topics, representative_image, dominant_color, updated_at, centroid, category)
                   VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE SET
                   tags = EXCLUDED.tags,
                   topics = EXCLUDED.topics,
                   representative_image = EXCLUDED.representative_image,
                   dominant_color = EXCLUDED.dominant_color,
                   updated_at = NOW(),
                   centroid = EXCLUDED.centroid,
                   category = EXCLUDED.category""",
                (
                    r["cluster_id"],
                    final_tags,
                    r["topics"],
                    rep_image,
                    dominant_color,
                    centroid_str,
                    r["dominant_category"],
                ),
                fetch=False,
            )
        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("cluster_metadata", "ok", "clusters:recent")
        if has_more:
            if pending_ids is not None:
                schedule_task_once(
                    "lock:cluster_metadata_batch",
                    120,
                    generate_cluster_metadata_task,
                    kwargs={"hours": hours, "target_clusters": pending_ids},
                    countdown=30,
                )
            else:
                schedule_task_once(
                    "lock:cluster_metadata_sweep",
                    120,
                    generate_cluster_metadata_task,
                    kwargs={"hours": hours},
                    countdown=30,
                )
    except Exception as e:
        from tasks import utils

        utils.record_task_event("cluster_metadata", "error", "clusters:recent")
        log.error(f"[tasks] Cluster metadata generation failed: {e}")


@celery_app.task(rate_limit="1/h")
def recluster_recent_articles_task(hours=24, limit=800):
    """Re-assign cluster IDs for recent articles using the current clustering logic."""
    try:
        import core.clustering as clustering

        hours = max(1, int(hours or 24))
        limit = max(1, int(limit or 800))
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        rows = (
            db.execute(
                """
            SELECT id, cluster_id, title, source, category, topic, created_at, embedding
            FROM articles
            WHERE created_at >= %s
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
                (cutoff, limit),
            )
            or []
        )

        if not rows:
            from tasks import utils

            utils.record_task_event("recluster_recent", "empty", f"hours:{hours}")
            return {
                "reclustered": 0,
                "touched_clusters": 0,
                "hours": hours,
                "limit": limit,
            }

        recent_articles = []
        batch_clusters = []
        updates = []
        touched_clusters = set()

        for row in rows:
            title = str(row.get("title") or "").strip()
            category = row.get("category")
            topic = str(row.get("topic") or "vesti").strip() or "vesti"
            source = row.get("source")
            created_at = row.get("created_at")
            parsed_embedding = parse_embedding_value(row.get("embedding"))

            new_cluster_id = None
            if parsed_embedding:
                for candidate in batch_clusters:
                    if candidate["category"] != category or candidate["topic"] != topic:
                        continue
                    dist = _cosine_dist(parsed_embedding, candidate["embedding"])
                    if dist >= (clustering.VECTOR_THRESHOLD * 0.78):
                        continue
                    if topic == "vesti" or not topic:
                        incoming_entities = clustering._extract_title_entities(title)
                        candidate_entities = candidate.get("entities", set())
                        shared_entities = (
                            incoming_entities.intersection(candidate_entities)
                            if incoming_entities and candidate_entities
                            else set()
                        )
                        phrase_overlap = clustering._cluster_title_overlap(title, candidate["title"])
                        if not shared_entities and phrase_overlap < 0.34:
                            continue
                    new_cluster_id = candidate["cid"]
                    break

            if not new_cluster_id:
                new_cluster_id = clustering.find_or_create_cluster(
                    None,
                    title,
                    recent_articles,
                    embedding=None,
                    category=category,
                    source=source,
                    topic=topic,
                )

            old_cluster_id = str(row.get("cluster_id") or "")
            if new_cluster_id != old_cluster_id:
                updates.append((new_cluster_id, row["id"]))
                if old_cluster_id:
                    touched_clusters.add(old_cluster_id)
                touched_clusters.add(new_cluster_id)

            if parsed_embedding:
                batch_clusters.append(
                    {
                        "cid": new_cluster_id,
                        "embedding": parsed_embedding,
                        "category": category,
                        "topic": topic,
                        "title": title,
                        "entities": clustering._extract_title_entities(title),
                    }
                )

            recent_articles.insert(
                0,
                {
                    "title": title,
                    "cluster_id": new_cluster_id,
                    "created_at": created_at,
                    "category": category,
                    "topic": topic,
                    "source": source,
                },
            )
            if len(recent_articles) > CLUSTER_LOOKBACK:
                recent_articles.pop()

        for cluster_id, article_id in updates:
            db.execute(
                "UPDATE articles SET cluster_id = %s WHERE id = %s",
                (cluster_id, article_id),
                fetch=False,
            )

        if touched_clusters:
            touched = sorted(touched_clusters)
            # Whitelist of tables that can be safely deleted from
            _ALLOWED_CLEANUP_TABLES = (
                "cluster_summaries",
                "cluster_metadata",
                "cluster_entities",
                "reactions",
            )
            for table in _ALLOWED_CLEANUP_TABLES:
                db.execute(
                    f"DELETE FROM {table} WHERE cluster_id = ANY(%s)",
                    (touched,),
                    fetch=False,
                )

            extract_entities_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=5)
            generate_cluster_metadata_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=5)
            auto_summarize_task.apply_async(args=(touched,), countdown=2)
            invalidate_public_data_caches()

        from tasks import utils

        utils.record_task_event("recluster_recent", "ok", f"articles:{len(updates)}")
        return {
            "reclustered": len(updates),
            "touched_clusters": len(touched_clusters),
            "hours": hours,
            "limit": limit,
        }
    except Exception as e:
        from tasks import utils

        utils.record_task_event("recluster_recent", "error", "clusters:recent")
        log.error(f"[tasks] Recent recluster failed: {e}")
        raise


@celery_app.task(rate_limit="1/h")
def repair_split_clusters_task(hours=48, limit=1200, dry_run=False):
    """Merge recent near-duplicate clusters that ingestion split too conservatively."""
    try:
        hours = max(1, int(hours or 48))
        limit = max(2, int(limit or 1200))
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        rows = db.execute(
            """
            SELECT a.cluster_id,
                   mode() WITHIN GROUP (ORDER BY a.country) as country,
                   mode() WITHIN GROUP (ORDER BY a.category) as category,
                   mode() WITHIN GROUP (ORDER BY a.topic) as topic,
                   COUNT(*) as article_count,
                   MIN(COALESCE(a.ingested_at, a.created_at)) as first_article,
                   MAX(COALESCE(a.ingested_at, a.created_at)) as latest_article,
                   array_agg(DISTINCT a.title) as titles,
                   COALESCE(cm.tags, '{}') as tags,
                   cm.centroid
            FROM articles a
            LEFT JOIN cluster_metadata cm ON cm.cluster_id = a.cluster_id
            WHERE COALESCE(a.ingested_at, a.created_at) >= %s
              AND a.cluster_id IS NOT NULL
            GROUP BY a.cluster_id, cm.tags, cm.centroid
            ORDER BY latest_article DESC
            LIMIT %s
            """,
            (cutoff, limit),
        ) or []

        candidates = []
        for i, left in enumerate(rows):
            for right in rows[i + 1 :]:
                lang = "mk" if left.get("country") == "MK" else "sr"
                score = _split_cluster_merge_score(left, right, lang=lang)
                if score > 0:
                    candidates.append((score, left, right))
        candidates.sort(key=lambda item: item[0], reverse=True)

        row_by_id = {row["cluster_id"]: row for row in rows}
        parent = {row["cluster_id"]: row["cluster_id"] for row in rows}

        def find(cluster_id):
            while parent.get(cluster_id, cluster_id) != cluster_id:
                parent[cluster_id] = parent.get(parent[cluster_id], parent[cluster_id])
                cluster_id = parent[cluster_id]
            return cluster_id

        def choose_target(left_id, right_id):
            left = row_by_id[left_id]
            right = row_by_id[right_id]
            left_count = int(left.get("article_count") or 0)
            right_count = int(right.get("article_count") or 0)
            if left_count > right_count:
                return left_id, right_id
            if right_count > left_count:
                return right_id, left_id
            return (
                (left_id, right_id)
                if (left.get("first_article") or datetime.datetime.max)
                <= (right.get("first_article") or datetime.datetime.max)
                else (right_id, left_id)
            )

        merge_scores = {}
        touched_clusters = set()
        for score, left, right in candidates:
            left_root = find(left["cluster_id"])
            right_root = find(right["cluster_id"])
            if left_root == right_root:
                continue

            target_id, source_id = choose_target(left_root, right_root)
            parent[source_id] = target_id
            merge_scores[source_id] = max(float(score), merge_scores.get(source_id, 0.0))
            touched_clusters.update({target_id, source_id})

        canonical_merges = []
        for source_id, score in sorted(merge_scores.items(), key=lambda item: item[1], reverse=True):
            target_id = find(source_id)
            if source_id != target_id:
                canonical_merges.append({"source": source_id, "target": target_id, "score": round(score, 4)})

        touched_clusters = set()
        for merge in canonical_merges:
            target_id = merge["target"]
            source_id = merge["source"]
            touched_clusters.update({target_id, source_id})

            if not dry_run:
                db.execute(
                    "UPDATE articles SET cluster_id = %s WHERE cluster_id = %s",
                    (target_id, source_id),
                    fetch=False,
                )

        if canonical_merges and not dry_run:
            touched = sorted(touched_clusters)
            for table in ("cluster_summaries", "cluster_metadata", "cluster_entities", "reactions"):
                db.execute(f"DELETE FROM {table} WHERE cluster_id = ANY(%s)", (touched,), fetch=False)

            extract_entities_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=5)
            generate_cluster_metadata_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=10)
            auto_summarize_task.apply_async(args=(touched,), countdown=20)
            invalidate_public_data_caches()

        from tasks import utils

        utils.record_task_event("repair_split_clusters", "ok", f"merges:{len(canonical_merges)}")
        return {"merges": canonical_merges, "dry_run": bool(dry_run), "hours": hours, "limit": limit}
    except Exception as e:
        from tasks import utils

        utils.record_task_event("repair_split_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Split cluster repair failed: {e}")
        raise


@celery_app.task
def auto_repair_sources_task():
    """Bridge to ingestion module for repair task."""
    from tasks.ingestion_task import auto_repair_sources_task as _task

    return _task()


@celery_app.task(rate_limit="5/m")
def backfill_cover_art_single_task(cluster_id, title):
    """Generate cover art for a single cluster without blocking a worker."""
    if get_celery_queue_depth() >= _BACKFILL_QUEUE_DEPTH_LIMIT:
        log.info(
            "[tasks] Skipping cover art generation for %s while queue backlog is high.",
            cluster_id,
        )
        return
    try:
        svg_content = generate_local_placeholder(cluster_id, title or "vest")
        img_url = generate_cover_art(cluster_id, svg_content)
        if img_url:
            db.execute(
                "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND image_url IS NULL",
                (img_url, cluster_id),
                fetch=False,
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art generation failed for {cluster_id}: {e}")


@celery_app.task
def backfill_cover_art_task():
    """Queue cover art generation for clusters that lack a strong visual."""
    lock_key = "lock:backfill_cover_art"
    cooldown_key = "ai:cover_art:pollinations:cooldown"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=1200):
            log.info("Cover art backfill already in progress, skipping duplicate dispatch.")
            return
    except Exception as e:
        log.warning(f"Redis lock check failed for backfill_cover_art: {e}")

    try:
        if get_celery_queue_depth() >= _BACKFILL_QUEUE_DEPTH_LIMIT:
            log.info("[tasks] Backfill cover art skipping: queue depth limit exceeded.")
            return

        try:
            if redis_client.get(cooldown_key):
                log.info("Cover art backfill paused due to Pollinations cooldown.")
                return
        except Exception as e:
            log.debug(f"Failed to check Redis cooldown: {e}")

        # Find clusters from last 24h that either:
        # 1. Have no representative image
        # 2. Have a representative image that would be considered 'weak' (placeholders, small thumbs)
        # But SKIP if we already generated AI art for them (to save credits)
        rows = db.execute(
            """
            SELECT DISTINCT a.cluster_id,
                   (SELECT summary FROM cluster_summaries WHERE cluster_id = a.cluster_id LIMIT 1) as summary,
                   (SELECT title FROM articles WHERE cluster_id = a.cluster_id ORDER BY created_at DESC LIMIT 1) as title
            FROM articles a
            LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
            WHERE a.created_at >= NOW() - INTERVAL '24 hours'
              AND (
                  m.representative_image IS NULL
                  OR m.representative_image LIKE '%.svg'
                  OR m.representative_image LIKE '%placeholder%'
                  OR m.representative_image LIKE '%default%'
              )
              AND (m.representative_image IS NULL OR m.representative_image NOT LIKE '/static/generated/%.jpg')
            LIMIT 12
        """
        )
        for idx, r in enumerate(rows):
            prompt_text = r["summary"] or r["title"] or ""
            backfill_cover_art_single_task.apply_async(
                args=(r["cluster_id"], prompt_text),
                countdown=idx * 5,  # Faster dispatch
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art backfill failed: {e}")


@celery_app.task
def generate_embeddings_task():
    """Generate pgvector embeddings for articles that don't have one yet."""
    try:
        from core.embeddings import embed_recent_articles

        embed_recent_articles()
    except Exception as e:
        log.warning(f"[tasks] Embedding generation failed: {e}")


@celery_app.task
def discover_storylines_task():
    """Discover evolving storylines from news clusters."""
    try:
        from core.topic_discovery import discovery_engine

        discovery_engine.run_discovery(lookback_hours=48)
        discovery_engine.refresh_storyline_metadata()
    except Exception as e:
        log.warning(f"[tasks] Storyline discovery failed: {e}")


def _is_grounded_synthesis(synthesis_text: str, source_context: str) -> bool:
    if not synthesis_text or not source_context:
        return True

    from nlp.keywords import _extract_capitalized_phrases
    from nlp.utils import transliterate

    source_latin = transliterate(source_context).casefold()
    context_entities = {
        transliterate(phrase).casefold()
        for phrase in _extract_capitalized_phrases(source_context)
        if len(str(phrase or "").strip()) >= 4
    }

    role_words = {
        "president",
        "prime",
        "minister",
        "premier",
        "serbian",
        "macedonian",
        "american",
        "russian",
        "ukrainian",
        "european",
        "pretsedatel",
        "pretsedatelot",
        "pretsedatelkata",
        "premierot",
        "premierkata",
        "premijer",
        "premijerka",
        "ministar",
        "ministarka",
        "ministerot",
        "ministerkata",
        "srpski",
        "srpska",
        "srpskog",
        "makedonski",
        "makedonska",
        "americki",
        "americka",
        "ruski",
        "ruska",
        "ukrajinski",
        "ukrajinska",
        "evropski",
        "evropska",
    }

    def _entity_words(value: str) -> list[str]:
        folded_value = transliterate(value or "").casefold()
        return [
            word
            for word in re.findall(r"[A-Za-z\u0400-\u04FF0-9-]{3,}", folded_value)
            if word not in role_words
        ]

    def _entity_is_grounded(value: str) -> bool:
        folded_value = transliterate(value or "").casefold().strip()
        if not folded_value:
            return True
        if folded_value in context_entities or folded_value in source_latin:
            return True

        words = _entity_words(value)
        if not words:
            return True

        # Role + partial name should pass when the actual name appears nearby in source.
        matched = 0
        for word in words:
            stem = word[:6] if len(word) > 7 else word
            if stem in source_latin or any(stem in entity for entity in context_entities):
                matched += 1

        if matched >= len(words):
            return True
        if len(words) >= 2 and matched >= len(words) - 1 and any(len(word) >= 6 for word in words):
            return True

        return False

    allowed_singletons = {
        "srbij",
        "beograd",
        "albanij",
        "eu",
        "vmro-dpmne",
        "iran",
        "ormuskiot tesnec",
        "dojran",
        "sad",
        "teksas",
        "nato",
        "obedinetite nacii",
        "on",
        "ukrain",
        "rusij",
        "sdsm",
        "vasington",
        "teheran",
        "bliskiot istok",
        "persiskiot zaliv",
        "zapadniot balkan",
        "evropskata unija",
        "brisel",
        "moskva",
        "kiev",
        "izrael",
        "gaza",
        "liban",
        "crna gora",
        "grcij",
        "bugarij",
        "makedon",
        "republik",
        "severn",
        "ahmet",
        "mickosk",
        "siljanovsk",
        "pendarovsk",
        "kovacevsk",
        "filipc",
        "gruevsk",
        "zaev",
        "presek",
        "bitol",
        "ohrid",
        "tetovo",
        "kumanovo",
        "gostivar",
        "skopj",
        "beograd",
        "vinic",
        "veles",
        "stip",
        "strumic",
        "prilep",
        "sri lanka",
        "kiribati",
        "si dzinping",
        "bajden",
        "tramp",
        "putin",
        "zelenski",
        "makron",
        "erdogan",
        "vucic",
        "rama",
        "osman",
        "maricic",
        "kostadinovska-stojcevska",
        "biserka",
        "bocvarski",
        "liga na sampioni",
        "premier liga",
        "real madrid",
        "barselona",
        "mancester junajted",
        "baern minhen",
        "stef kari",
        "lebron dzejms",
        "jokic",
        "doncic",
        "djokovic",
        "alkaraz",
        "siner",
        "janik siner",
        "vinisius",
        "vinisius zunior",
        "mbape",
        "haland",
        "elmas",
        "elif elmas",
        "pandev",
    }

    hard_hallucinations = 0
    soft_hallucinations = 0
    for phrase in _extract_capitalized_phrases(synthesis_text):
        clean = str(phrase or "").strip().replace("\n", " ")
        if len(clean) < 4:
            continue
        if clean.split()[0].lower() in {"od", "vo", "na", "so", "za", "niz", "u", "iz"}:
            clean_parts = clean.split()[1:]
            if not clean_parts:
                continue
            clean = " ".join(clean_parts)
            if len(clean) < 3:
                continue

        words = [part for part in clean.replace("-", " ").split() if part]
        is_acronym = clean.isupper()

        # Stricter check for multi-word entities (proper names)
        # Single words are often common nouns or noise, so we are more lenient
        if len(words) < 2 and not is_acronym:
            continue

        folded = transliterate(clean).casefold()
        if folded in context_entities:
            continue

        # Check allowed_singletons with word boundary awareness or as substrings for longer phrases
        is_allowed = False
        for allowed in allowed_singletons:
            if allowed == folded:
                is_allowed = True
                break
            if len(allowed) > 5 and allowed in folded:
                is_allowed = True
                break

        if is_allowed:
            continue

        if _entity_is_grounded(clean):
            continue

        core_words = _entity_words(clean)
        if is_acronym or len(core_words) >= 2:
            log.warning(f"[ai/hallucination] Hallucinated entity detected in synthesis: {clean} (folded: {folded})")
            hard_hallucinations += 1
        else:
            log.debug(f"[ai/hallucination] Suspicious but soft entity in synthesis: {clean} (folded: {folded})")
            soft_hallucinations += 1

    # Keep hard failures for truly ungrounded names, but allow a little noise from
    # translated titles and capitalization quirks in Serbian/Macedonian synthesis.
    if hard_hallucinations > 2:
        return False
    if hard_hallucinations >= 1 and len(synthesis_text) < 700:
        return False
    if hard_hallucinations >= 2 and len(synthesis_text) < 1400:
        return False
    if hard_hallucinations >= 1 and soft_hallucinations >= 4 and len(synthesis_text) < 1200:
        return False

    return True


@celery_app.task
def backfill_cluster_summaries_task(days=30, lang="sr", offset=0):
    """Generate cluster summaries for all existing clusters that don't have them yet."""
    try:
        if _queue_backlog_high():
            log.info(f"[tasks] Skipping summary backfill (lang={lang}) while queue backlog is high.")
            return

        from core.config import AUTO_SUMMARIZE_MIN_SRC
        from core.database import db_manager as db

        target_country = "MK" if lang == "mk" else "RS"

        # Get all clusters with articles but no summaries
        rows = db.execute(
            """
            SELECT DISTINCT a.cluster_id
            FROM articles a
            WHERE a.cluster_id IS NOT NULL
            AND a.country = %s
            AND a.created_at >= NOW() - make_interval(days => %s)
            AND NOT EXISTS (
                SELECT 1 FROM cluster_summaries cs
                WHERE cs.cluster_id = a.cluster_id AND cs.lang = %s
            )
            ORDER BY a.cluster_id
            LIMIT %s OFFSET %s
            """,
            (target_country, days, lang, _BACKFILL_BATCH_SIZE + 1, offset),
        )

        if not rows:
            log.info(f"[tasks] No clusters found for backfill (lang={lang})")
            return

        has_more = len(rows) > _BACKFILL_BATCH_SIZE
        cluster_ids = [row["cluster_id"] for row in rows[:_BACKFILL_BATCH_SIZE]]
        log.info(f"[tasks] Backfilling summaries for {len(cluster_ids)} clusters (lang={lang}, offset={offset})")

        for cluster_id in cluster_ids:
            try:
                # Check if this cluster has enough sources
                src_rows = db.execute(
                    "SELECT DISTINCT source FROM articles WHERE cluster_id = %s AND country = %s",
                    (cluster_id, target_country),
                )

                if len(src_rows) < AUTO_SUMMARIZE_MIN_SRC:
                    log.debug(f"[tasks] Skipping cluster {cluster_id} - only {len(src_rows)} source(s)")
                    continue

                # Load articles for this cluster
                article_rows = db.execute(
                    "SELECT * FROM articles WHERE cluster_id = %s AND country = %s ORDER BY created_at ASC",
                    (cluster_id, target_country),
                )

                if not article_rows:
                    continue

                system_prompt = SYNTHESIS_SYSTEM_PROMPT_MK if lang == "mk" else SYNTHESIS_SYSTEM_PROMPT_SR
                full_prompt = _build_cluster_synthesis_prompt(article_rows, lang=lang)
                cascade = _generate_synthesis_via_cascade(
                    article_rows,
                    full_prompt,
                    system_prompt,
                    lang=lang,
                    max_tokens=3000,
                    fast_mode=True,
                )
                generation_provider = cascade.get("provider")
                generation_model = cascade.get("model")
                fallback_reason = cascade.get("fallback_reason")

                if cascade["status"] == "success":
                    res_data = cascade["res_data"]
                    fallback_result = {
                        "summary": res_data.get("summary", ""),
                        "generated_article": res_data.get("article", "") or res_data.get("generated_article", ""),
                        "synthetic_headline": res_data.get("synthetic_headline", ""),
                        "synthetic_standfirst": res_data.get("synthetic_standfirst", ""),
                        "perspectives": res_data.get("perspectives", []),
                        "key_facts": res_data.get("key_facts", []),
                        "analyst_entities": res_data.get("analyst_entities", []),
                    }
                    if isinstance(fallback_result["summary"], list):
                        fallback_result["summary"] = "\n".join(str(s) for s in fallback_result["summary"])
                    fallback_reason = None
                else:
                    fallback_result = synthesize_cluster_fallback(article_rows, lang=lang)
                    generation_provider = "enhanced_fallback"
                    generation_model = "enhanced_fallback"
                    fallback_reason = "backfill_enhanced_fallback_after_cascade_exhausted"

                if fallback_result["summary"] or fallback_result["generated_article"]:
                    # Store the summary in database
                    db.execute(
                        """
                        INSERT INTO cluster_summaries
                        (cluster_id, lang, summary, generated_article, synthetic_headline,
                         synthetic_standfirst, created_at, perspectives, key_facts, analyst_entities,
                         generation_provider, generation_model, fallback_reason)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (cluster_id, lang) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        generated_article = EXCLUDED.generated_article,
                        synthetic_headline = EXCLUDED.synthetic_headline,
                        synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                        created_at = NOW(),
                        perspectives = EXCLUDED.perspectives,
                        key_facts = EXCLUDED.key_facts,
                        analyst_entities = EXCLUDED.analyst_entities,
                        generation_provider = EXCLUDED.generation_provider,
                        generation_model = EXCLUDED.generation_model,
                        fallback_reason = EXCLUDED.fallback_reason
                        """,
                        (
                            cluster_id,
                            lang,
                            fallback_result["summary"][:4000] if fallback_result["summary"] else "",
                            fallback_result["generated_article"][:8000] if fallback_result["generated_article"] else "",
                            (
                                fallback_result["synthetic_headline"][:200]
                                if fallback_result["synthetic_headline"]
                                else ""
                            ),
                            (
                                fallback_result["synthetic_standfirst"][:500]
                                if fallback_result["synthetic_standfirst"]
                                else ""
                            ),
                            json.dumps(fallback_result["perspectives"][:2000] if fallback_result["perspectives"] else []),
                            json.dumps(fallback_result.get("key_facts")[:1000] if fallback_result.get("key_facts") else []),
                            json.dumps(fallback_result.get("analyst_entities")[:1000] if fallback_result.get("analyst_entities") else []),
                            generation_provider,
                            generation_model,
                            fallback_reason,
                        ),
                    )
                    record_runtime_event("synthesis_path", mode=generation_provider, fast_mode=False, lang=lang)
                    log.info(f"[tasks] Generated summary for cluster {cluster_id} (lang={lang})")
                else:
                    log.debug(f"[tasks] No summary generated for cluster {cluster_id}")

            except Exception as e:
                log.warning(f"[tasks] Failed to generate summary for cluster {cluster_id}: {e}")

        log.info(f"[tasks] Completed backfill for {lang} language clusters")
        if has_more:
            schedule_task_once(
                f"lock:backfill_summaries:{lang}",
                180,
                backfill_cluster_summaries_task,
                kwargs={"days": days, "lang": lang, "offset": offset + _BACKFILL_BATCH_SIZE},
                countdown=60,
            )

    except Exception as e:
        log.error(f"[tasks] Backfill cluster summaries failed: {e}")
        raise


@celery_app.task
def refine_knowledge_graph_sentiment_task():
    """Asynchronously refine entities and relationships in the knowledge graph using deep LLM sentiment analysis."""
    try:
        # Fetch articles from the last 2 hours
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=2)
        rows = db.execute(
            """
            SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
            FROM articles
            WHERE created_at >= %s
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT source) >= 2
            LIMIT 20
            """,
            (cutoff,),
        )
        
        if not rows:
            log.info("[sentiment-refinement] No active clusters to refine sentiment for.")
            return

        from core.entities import extract_entities
        from nlp import analyze_sentiment_locally

        refined_count = 0
        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"
            
            # Extract the unique entities
            entities = extract_entities(text, max_entities=8)
            if not entities:
                continue
                
            # Run deep context-aware LLM sentiment analysis (bypass_llm=False)
            deep_sentiment = analyze_sentiment_locally(text, bypass_llm=False)
            
            for ent in entities:
                from core.entities import normalize_entity_name
                canonical_name = normalize_entity_name(ent["name"])
                
                # Blend the deep sentiment score into the existing database score
                db.execute(
                    """
                    UPDATE knowledge_entities
                    SET sentiment_score = (sentiment_score * 0.7) + (%s * 0.3),
                        last_seen = CURRENT_TIMESTAMP
                    WHERE name = %s
                    """,
                    (deep_sentiment, canonical_name),
                    fetch=False,
                )
                refined_count += 1
                
        log.info(f"[sentiment-refinement] Successfully refined deep sentiment for {refined_count} entities.")
        
    except Exception as e:
        log.error(f"[sentiment-refinement] Failed to refine knowledge graph sentiment: {e}")
