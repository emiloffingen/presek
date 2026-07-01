"""SR→MK synthesis translation with grounding and copy-purity gates."""

from __future__ import annotations

import json

from core.ai_engine import clean_json_response
from core.ai_engine import sync_call_ai as _call_ai
from tasks.intelligence.synthesis_grounding import _is_fact_grounded_synthesis
from tasks.utils import log


def _resolve_generation_model(provider: str | None):
    if not provider:
        return None
    from core.ai_engine import PROVIDERS

    provider_obj = PROVIDERS.get(provider)
    if provider_obj and getattr(provider_obj, "model", None):
        return provider_obj.model
    return provider


def try_translate_synthesis_to_mk(sr_bundle, article_rows, fast_mode=False):
    """Translate a successful Serbian synthesis bundle to Macedonian."""
    from core.runtime_limits import SYNTHESIS_MK_TRANSLATE_FROM_SR

    if not SYNTHESIS_MK_TRANSLATE_FROM_SR or not sr_bundle:
        return None

    payload = {
        "synthetic_headline": sr_bundle.get("synthetic_headline", ""),
        "synthetic_standfirst": sr_bundle.get("synthetic_standfirst", ""),
        "summary": sr_bundle.get("summary", ""),
        "article": sr_bundle.get("generated_article", ""),
        "key_facts": sr_bundle.get("key_facts", []),
        "perspectives": sr_bundle.get("perspectives", []),
        "verification_report": sr_bundle.get("verification_report"),
        "sentiment": sr_bundle.get("sentiment", {}),
        "tone_analysis": sr_bundle.get("tone_analysis", {}),
        "story_so_far": sr_bundle.get("story_so_far", ""),
        "impact_analysis": sr_bundle.get("impact_analysis", {}),
        "quote": sr_bundle.get("quote", ""),
    }
    translate_prompt = (
        "Преведи ја следната уредничка синтеза од српски (латиница) на чист македонски литературен јазик (кирилица).\n"
        "Задржи ја истата JSON структура и истите информациски слоеви; не додавај нови факти.\n"
        "Врати САМО валиден JSON со истите клучеви како влезот.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    strict_suffix = (
        "\n\nКРИТИЧНО: Целосниот излез мора да биде на чист македонски кирилица. "
        "Не користи латиница освен за скратеници (NATO, EU) и цитати [1]."
    )
    attempts = [
        (
            "Ти си професионален преведувач за вести од српски на македонски јазик.",
            translate_prompt,
        ),
        (
            "Ти си строг уредник. Преведи на чист македонски кирилица без српски латинични зборови.",
            translate_prompt + strict_suffix,
        ),
    ]
    try:
        for attempt_idx, (system_prompt, prompt_body) in enumerate(attempts):
            raw_trans, provider = _call_ai(
                prompt=prompt_body,
                system=system_prompt,
                task_type="translation",
                max_tokens=4000 if not fast_mode else 2200,
                json_mode=True,
                lang="mk",
            )
            if not raw_trans:
                continue
            trans_data = clean_json_response(raw_trans)
            if not isinstance(trans_data, dict):
                continue
            summary = trans_data.get("summary", "")
            generated_article = trans_data.get("article", "") or trans_data.get("generated_article", "")
            if isinstance(summary, list):
                summary = "\n".join(str(s) for s in summary)
            comparison_text = f"{summary}\n{generated_article}"
            if not summary or not generated_article:
                continue
            if not _is_fact_grounded_synthesis(comparison_text, article_rows, "mk", fast_mode=fast_mode):
                log.warning(
                    "[tasks/synthesis] MK translation attempt %s failed fact grounding gate",
                    attempt_idx + 1,
                )
                continue
            from core.copy_quality import copy_bundle_passes_publish_gate

            mk_ok, mk_diag = copy_bundle_passes_publish_gate(
                lang="mk",
                headline=trans_data.get("synthetic_headline", ""),
                summary=summary,
                article=generated_article,
                key_facts=trans_data.get("key_facts", []),
            )
            if not mk_ok:
                log.warning(
                    "[tasks/synthesis] MK translation attempt %s failed copy purity gate: %s",
                    attempt_idx + 1,
                    mk_diag,
                )
                continue
            return {
                "status": "success",
                "provider": provider or "translation",
                "model": _resolve_generation_model(provider) if provider else "translation",
                "fallback_reason": "translated_from_sr",
                "res_data": trans_data,
                "quality_score": sr_bundle.get("quality_score"),
                "raw": raw_trans,
                "cascade_depth": attempt_idx + 1,
            }
        return None
    except Exception as exc:
        log.warning(f"[tasks/synthesis] MK translation from SR failed: {exc}")
        return None
