"""Provider cascade, candidate evaluation, and local Gemma rescue."""

from __future__ import annotations

from core.ai_engine import clean_json_response
from tasks.intelligence._constants import _call_ai
from tasks.intelligence.synthesis_grounding import (
    _fact_grounding_diagnostics,
    _is_grounded_synthesis,
)
from tasks.intelligence.synthesis_scoring import (
    _score_editorial_summary,
    _score_synthesis_quality,
)
from tasks.utils import log

def _resolve_generation_model(provider: str | None):
    if not provider:
        return None
    from core.ai_engine import PROVIDERS

    provider_obj = PROVIDERS.get(provider)
    if provider_obj and getattr(provider_obj, "model", None):
        return provider_obj.model
    return provider


def _evaluate_synthesis_candidate(
    res_data,
    *,
    provider,
    article_rows,
    lang,
    fast_mode,
    current_context,
    legacy_summary,
):
    """Apply grounding and tiered quality gates to a parsed synthesis payload."""
    from core.synthesis_quality import synthesis_quality_threshold

    summary = res_data.get("summary", "")
    generated_article = res_data.get("article", "") or res_data.get("generated_article", "")
    synthetic_headline = res_data.get("synthetic_headline", "")
    if isinstance(summary, list):
        summary = "\n".join(str(s) for s in summary)

    if not summary or not generated_article:
        return None, "partial_response", None

    comparison_text = f"{summary}\n{generated_article}"
    grounding = _fact_grounding_diagnostics(comparison_text, article_rows, lang, fast_mode=fast_mode)
    if not grounding["ok"]:
        return None, "fact_grounding_failed", grounding

    if not fast_mode and not _is_grounded_synthesis(comparison_text, current_context or legacy_summary):
        return None, "hallucination_gate_failed", None

    key_facts = res_data.get("key_facts", [])
    article_score = _score_synthesis_quality(synthetic_headline, generated_article, key_facts, lang)
    summary_score = _score_editorial_summary(summary, generated_article, lang)
    quality_score = round((article_score * 0.65) + (summary_score * 0.35), 3)
    threshold = synthesis_quality_threshold(provider, fast_mode=fast_mode)
    if threshold is not None and quality_score < threshold:
        return None, "failed_quality_score", None

    if lang == "mk":
        from core.copy_quality import copy_bundle_passes_publish_gate

        copy_ok, copy_diag = copy_bundle_passes_publish_gate(
            lang="mk",
            headline=synthetic_headline,
            summary=summary,
            article=generated_article,
            key_facts=key_facts if isinstance(key_facts, list) else [],
        )
        if not copy_ok:
            return None, "mk_copy_purity_failed", copy_diag
    elif lang == "sr":
        from core.copy_quality import copy_bundle_passes_publish_gate

        copy_ok, copy_diag = copy_bundle_passes_publish_gate(
            lang="sr",
            headline=synthetic_headline,
            summary=summary,
            article=generated_article,
            key_facts=key_facts if isinstance(key_facts, list) else [],
        )
        if not copy_ok:
            return None, "sr_copy_purity_failed", copy_diag

    return {
        "quality_score": quality_score,
        "summary": summary,
        "generated_article": generated_article,
        "synthetic_headline": synthetic_headline,
    }, None, None


def _grounding_retry_suffix(lang: str, diagnostics: dict | None) -> str:
    nums = (diagnostics or {}).get("ungrounded_numbers") or []
    scores = (diagnostics or {}).get("ungrounded_scores") or []
    hints: list[str] = []
    if nums:
        hints.append(", ".join(nums[:3]))
    if scores:
        hints.append(", ".join(scores[:2]))
    hint = f" {'; '.join(hints)}." if hints else "."
    if lang == "mk":
        return (
            "\n\nКРИТИЧНО: Користи САМО броеви, резултати и датуми што се појавуваат во изворите."
            f" Не додавај непотврдени бројки{hint}"
        )
    return (
        "\n\nKRITICNO: Koristi SAMO brojeve, rezultate i datume koji se pojavljuju u izvorima."
        f" Ne dodaj nepotvrdene brojke{hint}"
    )


def _attempt_gemma_rescue(
    article_rows,
    full_prompt,
    system_prompt,
    lang,
    max_tokens,
    fast_mode,
    current_context,
    legacy_summary,
    exclude_providers,
):
    """Explicit local/Gemma attempt before deterministic fallback."""
    from core.limits import SYNTHESIS_GEMMA_BEFORE_DETERMINISTIC, local_synthesis_enabled
    from core.llm_router import _local_model_available

    if (
        not SYNTHESIS_GEMMA_BEFORE_DETERMINISTIC
        or not local_synthesis_enabled()
        or not _local_model_available()
    ):
        return None
    if "local" in exclude_providers:
        return None

    remote = ["nvidia"]
    raw, provider = _call_ai(
        full_prompt,
        system_prompt,
        json_mode=True,
        task_type="synthesis",
        max_tokens=max_tokens,
        lang=lang,
        provider_override="local",
        exclude_providers=[p for p in remote if p not in exclude_providers],
    )
    if not raw or provider != "local":
        return None
    try:
        res_data = clean_json_response(raw)
        if not isinstance(res_data, dict):
            return None
    except Exception:
        return None

    evaluated, fail_reason, grounding_diag = _evaluate_synthesis_candidate(
        res_data,
        provider="local",
        article_rows=article_rows,
        lang=lang,
        fast_mode=fast_mode,
        current_context=current_context,
        legacy_summary=legacy_summary,
    )
    if not evaluated:
        log.warning(
            "[tasks/synthesis] Gemma rescue failed: %s (%s)",
            fail_reason,
            grounding_diag or {},
        )
        return None

    return {
        "status": "success",
        "provider": "local",
        "model": _resolve_generation_model("local"),
        "fallback_reason": "gemma_rescue",
        "res_data": res_data,
        "quality_score": evaluated["quality_score"],
        "raw": raw,
    }


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
    grounding_retried: set[str] = set()
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
            if provider:
                exclude_providers.append(provider)
            break

        try:
            res_data = clean_json_response(raw)
            if not isinstance(res_data, dict):
                raise ValueError("Parsed JSON is not a dictionary")
        except Exception as exc:
            log.error(f"[tasks/synthesis] JSON parse error from {provider}: {exc}")
            if last_fallback_reason != "malformed_json":
                last_fallback_reason = "malformed_json"
                compact_suffix = (
                    "\n\nKRITICNO: Vrati SAMO validan JSON objekat bez markdown-a, bez uvoda i bez komentara."
                    if lang == "sr"
                    else "\n\nКРИТИЧНО: Врати САМО валиден JSON објект без markdown, без вовед и без коментари."
                )
                retry_raw, retry_provider = _call_ai(
                    full_prompt + compact_suffix,
                    system_prompt + " Output must be a single JSON object only.",
                    json_mode=True,
                    task_type="synthesis",
                    max_tokens=max_tokens,
                    lang=lang,
                    provider_override=provider,
                    exclude_providers=[p for p in exclude_providers if p != provider],
                )
                if retry_raw and retry_provider:
                    try:
                        res_data = clean_json_response(retry_raw)
                        if isinstance(res_data, dict):
                            raw = retry_raw
                            provider = retry_provider
                        else:
                            raise ValueError("Retry JSON is not a dictionary")
                    except Exception as retry_exc:
                        log.warning(f"[tasks/synthesis] JSON retry failed for {provider}: {retry_exc}")
                        exclude_providers.append(provider)
                        continue
                else:
                    exclude_providers.append(provider)
                    continue
            else:
                exclude_providers.append(provider)
                continue

        evaluated, fail_reason, grounding_diag = _evaluate_synthesis_candidate(
            res_data,
            provider=provider,
            article_rows=article_rows,
            lang=lang,
            fast_mode=fast_mode,
            current_context=current_context,
            legacy_summary=legacy_summary,
        )
        if not evaluated:
            if fail_reason == "fact_grounding_failed" and provider not in grounding_retried:
                grounding_retried.add(provider)
                log.warning(
                    "[tasks/synthesis] Grounding retry for %s: %s",
                    provider,
                    grounding_diag or {},
                )
                retry_raw, retry_provider = _call_ai(
                    full_prompt + _grounding_retry_suffix(lang, grounding_diag),
                    system_prompt + " Use only numbers and scores present in the source articles.",
                    json_mode=True,
                    task_type="synthesis",
                    max_tokens=max_tokens,
                    lang=lang,
                    provider_override=provider,
                    exclude_providers=[p for p in exclude_providers if p != provider],
                )
                if retry_raw and retry_provider:
                    try:
                        retry_data = clean_json_response(retry_raw)
                        if isinstance(retry_data, dict):
                            retry_evaluated, retry_fail, _retry_diag = _evaluate_synthesis_candidate(
                                retry_data,
                                provider=retry_provider,
                                article_rows=article_rows,
                                lang=lang,
                                fast_mode=fast_mode,
                                current_context=current_context,
                                legacy_summary=legacy_summary,
                            )
                            if retry_evaluated:
                                return {
                                    "status": "success",
                                    "provider": retry_provider,
                                    "model": _resolve_generation_model(retry_provider),
                                    "fallback_reason": "grounding_retry",
                                    "res_data": retry_data,
                                    "quality_score": retry_evaluated["quality_score"],
                                    "raw": retry_raw,
                                    "cascade_depth": len(exclude_providers) + 1,
                                }
                            last_fallback_reason = retry_fail
                    except Exception as retry_exc:
                        log.warning(
                            "[tasks/synthesis] Grounding retry parse failed for %s: %s",
                            provider,
                            retry_exc,
                        )

            log.warning(f"[tasks/synthesis] Gate failed for provider {provider}: {fail_reason}")
            last_fallback_reason = fail_reason
            exclude_providers.append(provider)
            continue

        return {
            "status": "success",
            "provider": provider,
            "model": _resolve_generation_model(provider),
            "fallback_reason": None,
            "res_data": res_data,
            "quality_score": evaluated["quality_score"],
            "raw": raw,
            "cascade_depth": len(exclude_providers) + 1,
        }

    rescue = _attempt_gemma_rescue(
        article_rows,
        full_prompt,
        system_prompt,
        lang,
        max_tokens,
        fast_mode,
        current_context,
        legacy_summary,
        exclude_providers,
    )
    if rescue:
        rescue["cascade_depth"] = len(exclude_providers) + 1
        return rescue

    return {
        "status": "exhausted",
        "provider": None,
        "model": None,
        "fallback_reason": last_fallback_reason or "cascade_exhausted",
        "res_data": None,
        "quality_score": None,
        "raw": None,
        "cascade_depth": len(exclude_providers),
    }
