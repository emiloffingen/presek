"""Reader-facing trust summaries for cluster cards and detail pages."""

from __future__ import annotations


def build_trust_summary(
    *,
    sources_count: int,
    pluralism_score: int | float | None = None,
    is_stale: bool = False,
    has_verification: bool = False,
    lang: str = "sr",
) -> dict:
    pluralism = int(pluralism_score or 0)
    score = min(
        100,
        max(
            0,
            min(sources_count, 8) * 10
            + (25 if pluralism <= 15 else 12 if pluralism >= 55 else 18)
            + (0 if is_stale else 20)
            + (10 if has_verification else 0),
        ),
    )

    if sources_count < 2:
        tier = "early"
        if lang == "mk":
            label = "Ран сигнал"
            detail = "Сè уште една редакција — третирајте го како почетен извештај."
        else:
            label = "Rani signal"
            detail = "Još jedna redakcija — tretirajte kao početni izveštaj."
    elif pluralism >= 55:
        tier = "plural"
        if lang == "mk":
            label = "Плурализам"
            detail = f"{sources_count} извори, различни нагласи ({pluralism}%)."
        else:
            label = "Pluralizam"
            detail = f"{sources_count} izvora, različiti naglasci ({pluralism}%)."
    elif pluralism <= 15:
        tier = "consensus"
        if lang == "mk":
            label = "Консензус"
            detail = f"{sources_count} извори покриваат иста приказна."
        else:
            label = "Konsenzus"
            detail = f"{sources_count} izvora pokrivaju istu priču."
    else:
        tier = "verified"
        if lang == "mk":
            label = "Проверено"
            detail = f"{sources_count} независни извори се следат."
        else:
            label = "Provereno"
            detail = f"{sources_count} nezavisna izvora se prate."

    if is_stale:
        if lang == "mk":
            detail = f"{detail} Синтезата се ажурира."
        else:
            detail = f"{detail} Sinteza se ažurira."

    return {
        "score": score,
        "tier": tier,
        "label": label,
        "detail": detail,
        "sources_count": sources_count,
        "pluralism_score": pluralism if pluralism_score is not None else None,
        "is_stale": is_stale,
        "has_verification": has_verification,
    }
