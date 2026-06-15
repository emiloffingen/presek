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
from nlp.utils import extract_clean_summary_text
from tasks.synthesis_sanitize import sanitize_synthesis_outputs as _sanitize_synthesis_outputs
from tasks.utils import (
    acquire_task_lock,
    get_celery_queue_depth,
    invalidate_cluster_caches,
    invalidate_public_data_caches,
    log,
    record_runtime_event,
    redis_client,
    release_task_lock,
    schedule_task_once,
)
from utils import get_dominant_color

from tasks.intelligence._constants import *  # noqa: F403

import datetime
import json
import os
import re
import sys
import threading

from tasks.intelligence._queue import intelligence_soft_deferred

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


def _build_source_comparison_prompt_block(article_rows, lang="sr"):
    from nlp.generation import compare_cluster_sources

    comparison = compare_cluster_sources(article_rows, lang=lang)
    lines = []
    if comparison.get("common_line"):
        lines.append(comparison["common_line"])
    for point in comparison.get("difference_points", [])[:2]:
        lines.append(point)
    for point in comparison.get("open_points", [])[:2]:
        lines.append(point)
    if not lines:
        return ""

    if lang == "mk":
        header = (
            "Локална анализа на изворите (користи ја при споредба на извори и непознати детали):\n"
            "<source_comparison>"
        )
        footer = "</source_comparison>"
    else:
        header = (
            "Lokalna analiza izvora (koristi pri poređenju izvora i nepotvrđenim detaljima):\n"
            "<source_comparison>"
        )
        footer = "</source_comparison>"
    return f"{header}\n" + "\n".join(f"- {line}" for line in lines) + f"\n{footer}"


def _fetch_synthesis_history_context(cluster_id, lang="sr", article_rows=None):
    try:
        from core.embeddings import get_cluster_embedding
        from core.config import HISTORY_SEMANTIC_THRESHOLD

        current_vec = get_cluster_embedding(cluster_id)
        if not current_vec:
            return ""

        current_vec_str = "[" + ",".join(map(str, current_vec)) + "]"
        related = db.execute(
            """
            SELECT s.summary, s.generated_article, a.title
            FROM cluster_summaries s
            JOIN articles a ON s.cluster_id = a.cluster_id
            JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
            WHERE s.cluster_id != %s
              AND s.lang = %s
              AND s.created_at >= NOW() - INTERVAL '7 days'
              AND s.created_at < (SELECT MIN(created_at) FROM articles WHERE cluster_id = %s)
              AND (m.centroid <=> %s::vector) < %s
            ORDER BY m.centroid <=> %s::vector
            LIMIT 1
        """,
            (cluster_id, lang, cluster_id, current_vec_str, HISTORY_SEMANTIC_THRESHOLD, current_vec_str),
        )
        if not related:
            return ""

        prev_text = related[0]["generated_article"] or related[0]["summary"]
        if not prev_text:
            return ""

        if lang == "mk":
            return (
                "Претходен контекст (за поврзана тема од изминатите денови):\n"
                f"<historical_context>\n{prev_text[:1000]}\n</historical_context>"
            )
        return (
            "PRETHODEN kontekst (za ovoj nastan ili povrzana tema od izminatite denovi):\n"
            f"<historical_context>\n{prev_text[:1000]}\n</historical_context>"
        )
    except Exception as e:
        log.warning(f"[tasks/memory] Failed to fetch history for {cluster_id} ({lang}): {e}")
        return ""


def _synthesis_source_corpus(article_rows):
    return " ".join(
        part
        for article in article_rows or []
        for part in (
            str(article.get("title") or ""),
            str(article.get("description") or ""),
            str(article.get("full_content") or ""),
            str(article.get("summary") or ""),
        )
        if part
    )


def _normalize_number_token(token: str) -> str:
    import re

    clean = str(token or "").strip().rstrip("%")
    if not clean:
        return ""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", clean):
        return clean.replace(".", "")
    if "," in clean and "." not in clean:
        left, _, right = clean.partition(",")
        if right.isdigit() and len(right) <= 2:
            return f"{left}.{right}"
    return clean.replace(",", ".")


def _is_soft_number_token(token: str) -> bool:
    import re

    clean = str(token or "").strip().rstrip("%")
    if re.fullmatch(r"20[12]\d", clean):
        return True
    if re.fullmatch(r"19\d{2}", clean):
        return True
    return False


def _number_token_grounded_in_source(token, source_numbers, source_text_folded):
    clean = str(token or "").strip()
    if not clean:
        return True
    if _is_soft_number_token(clean):
        normalized_year = _normalize_number_token(clean)
        if any(_normalize_number_token(src) == normalized_year for src in source_numbers):
            return True
        if clean.casefold() in source_text_folded:
            return True
    if clean in source_numbers:
        return True
    if clean.casefold() in source_text_folded:
        return True
    normalized = _normalize_number_token(clean)
    if not normalized:
        return True
    if normalized.casefold() in source_text_folded:
        return True
    for src in source_numbers:
        if _normalize_number_token(src) == normalized:
            return True
    normalized_legacy = clean.replace(",", ".")
    for src in source_numbers:
        src_norm = str(src).replace(",", ".")
        if normalized_legacy == src_norm:
            return True
    return False


def _is_fact_grounded_synthesis(synthesis_text: str, article_rows, lang: str = "sr", *, fast_mode: bool = False) -> bool:
    if not synthesis_text or not article_rows:
        return True

    from core.limits import FACT_GROUNDING_MAX_UNGROUNDED, FACT_GROUNDING_MAX_UNGROUNDED_FAST
    from nlp.generation import _extract_number_tokens, _extract_sports_scores
    from nlp.utils import transliterate

    source_text = transliterate(_synthesis_source_corpus(article_rows))
    source_folded = source_text.casefold()
    source_numbers = set(_extract_number_tokens(source_text))
    source_scores = set(_extract_sports_scores(source_text))

    synth_text = transliterate(str(synthesis_text or ""))
    synth_numbers = _extract_number_tokens(synth_text)
    synth_scores = _extract_sports_scores(synth_text)

    ungrounded_numbers = [
        token
        for token in synth_numbers
        if not _is_soft_number_token(token)
        and not _number_token_grounded_in_source(token, source_numbers, source_folded)
    ]
    max_ungrounded = FACT_GROUNDING_MAX_UNGROUNDED_FAST if fast_mode else FACT_GROUNDING_MAX_UNGROUNDED
    if len(ungrounded_numbers) > max_ungrounded:
        log.warning(
            "[ai/fact_gate] Ungrounded numbers in synthesis: %s",
            ", ".join(ungrounded_numbers[:4]),
        )
        return False

    if synth_scores:
        ungrounded_scores = [
            score
            for score in synth_scores
            if score not in source_scores and score.casefold() not in source_folded
        ]
        max_ungrounded_scores = 1 if fast_mode else 0
        if len(ungrounded_scores) > max_ungrounded_scores:
            log.warning("[ai/fact_gate] Ungrounded sports scores in synthesis: %s", ", ".join(ungrounded_scores))
            return False

    return True


def _build_cluster_synthesis_prompt(article_rows, lang="sr", history_context="", legacy_summary="", source_comparison=""):
    rows = article_rows or []
    prompt_parts = []
    if history_context:
        prompt_parts.append(history_context)
    if source_comparison:
        prompt_parts.append(source_comparison)
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
            "и што останува непознато или следно за проверка. "
            "Не измислувај броеви, проценти или резултати — користи само бројки што се појавуваат во изворите."
        )
    else:
        prompt_parts.append(
            "UREĐIVAČKI FOKUS: rezime ne sme biti lista naslova. "
            "Izvedi 3-4 pametne tačke: novi razvoj, zašto je važan, šta je zaista potvrđeno "
            "i šta ostaje nepoznato ili sledeće za proveru. "
            "Ne izmišljaj brojeve, procente ili rezultate — koristi samo brojke koje se pojavljuju u izvorima."
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
        if not _is_fact_grounded_synthesis(comparison_text, article_rows, lang, fast_mode=fast_mode):
            log.warning(f"[tasks/synthesis] Fact grounding gate failed for provider {provider}")
            last_fallback_reason = "fact_grounding_failed"
            exclude_providers.append(provider)
            continue

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


def _paragraph_fingerprint(text: str) -> str:
    return re.sub(r"\W+", " ", str(text or "").casefold()).strip()


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
        if len(meaningful_shared_tags) >= 2 and lexical >= 0.30:
            return round(lexical + phrase + len(meaningful_shared_tags) * 0.08 + centroid_similarity * 0.2, 4)
        if len(meaningful_shared_tags) >= 1 and lexical >= 0.24 and centroid_similarity >= 0.78:
            return round(lexical + phrase + centroid_similarity * 0.35, 4)
        return 0.0

    if lexical >= 0.36 or (phrase >= 0.22 and meaningful_shared_tags):
        return round(lexical + phrase + len(meaningful_shared_tags) * 0.06 + centroid_similarity * 0.15, 4)
    return 0.0


def _compute_lightweight_quality_score(synthetic_headline, summary, generated_article, key_facts, lang="sr"):
    article_score = _score_synthesis_quality(synthetic_headline, generated_article, key_facts, lang)
    summary_score = _score_editorial_summary(summary, generated_article, lang)
    return round((article_score * 0.65) + (summary_score * 0.35), 3)


def _schedule_fast_synthesis_upgrade(cluster_id: str, content=None) -> bool:
    """Queue a deferred full-quality synthesis after an initial fast-mode publish."""
    if os.environ.get("FAST_SYNTHESIS_UPGRADE_ENABLED", "true").lower() != "true":
        return False

    lock_key = f"lock:fast_synthesis_upgrade:{cluster_id}"
    scheduled = schedule_task_once(
        lock_key,
        _FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS,
        upgrade_fast_synthesis_task,
        args=(cluster_id,),
        kwargs={"content": content, "defer_attempt": 0},
        countdown=_FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS,
    )
    if scheduled:
        log.info(
            "[tasks/synthesis] Scheduled full upgrade for %s in %ss",
            cluster_id,
            _FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS,
        )
    return scheduled


@celery_app.task(name="tasks.intelligence.upgrade_fast_synthesis_task")
def upgrade_fast_synthesis_task(cluster_id, content=None, defer_attempt=0):
    """Run full-quality synthesis after fast-mode publish, deferring when intel-heavy is congested."""
    if intelligence_soft_deferred() and defer_attempt < _FAST_SYNTHESIS_UPGRADE_MAX_DEFERS:
        retry_delay = min(900, 120 * (defer_attempt + 1))
        log.info(
            "[tasks/synthesis] Deferring full upgrade for %s (attempt %s, retry in %ss)",
            cluster_id,
            defer_attempt + 1,
            retry_delay,
        )
        upgrade_fast_synthesis_task.apply_async(
            args=(cluster_id,),
            kwargs={"content": content, "defer_attempt": defer_attempt + 1},
            countdown=retry_delay,
        )
        return {"status": "deferred", "cluster_id": cluster_id, "defer_attempt": defer_attempt + 1}

    synthesize_cluster_task(cluster_id, content, fast_mode=False)
    return {"status": "upgraded", "cluster_id": cluster_id}


@celery_app.task(name="tasks.intelligence.synthesize_urgent_task", 
    queue="fast-track",
    rate_limit="60/m",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def synthesize_urgent_task(cluster_id, content=None):
    """Priority synthesis for new clusters."""
    return synthesize_cluster_task(cluster_id, content, fast_mode=True)


@celery_app.task(name="tasks.intelligence.synthesize_cluster_task", rate_limit="60/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0, fast_mode=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    citation_sources = _build_citation_sources(article_rows)
    target_langs = _langs_for_cluster_articles(article_rows)
    source_context_sr = _build_synthesis_source_context(article_rows, lang="sr")
    source_context_mk = _build_synthesis_source_context(article_rows, lang="mk")

    # Non-fast synthesis needs room for a longer editorial article plus the surrounding JSON fields.
    max_tokens = 2200 if fast_mode else 5200

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
    fast_synthesis_succeeded = False

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
            else:
                history_context = _fetch_synthesis_history_context(cluster_id, lang=lang, article_rows=article_rows)
                if history_context:
                    prompt_parts.append(history_context)

            source_comparison = _build_source_comparison_prompt_block(article_rows, lang=lang)
            if source_comparison:
                prompt_parts.append(source_comparison)

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
                if fast_mode:
                    if quality_score is None:
                        quality_score = _compute_lightweight_quality_score(
                            synthetic_headline,
                            summary,
                            generated_article,
                            res_data.get("key_facts", []),
                            lang=lang,
                        )
                record_runtime_event("synthesis_path", mode=provider or "unknown", fast_mode=fast_mode, lang=lang)
                
                # Record quality feedback for router
                if provider and quality_score is not None:
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
                if fast_mode:
                    fast_synthesis_succeeded = True
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

    if fast_mode and fast_synthesis_succeeded:
        _schedule_fast_synthesis_upgrade(cluster_id, legacy_summary or None)

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

_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

