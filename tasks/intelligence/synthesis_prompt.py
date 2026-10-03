"""Cluster synthesis prompt assembly and article context loading."""

from __future__ import annotations

from tasks.intelligence._constants import COUNTRY_LANG, db
from tasks.utils import log


def _load_cluster_articles_for_synthesis(cluster_id):
    return db.execute(
        "SELECT title, description, summary, full_content, source, link, created_at, category, topic, country, embedding FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )


def _langs_for_cluster_articles(article_rows):
    countries = {
        str(row.get("country") or "").upper() for row in (article_rows or []) if str(row.get("country") or "").strip()
    }
    langs = [COUNTRY_LANG[country] for country in ("RS", "MK") if country in countries]
    return langs or ["sr"]


def _order_synthesis_langs(target_langs):
    """Serbian first when bilingual so Macedonian can be translated from SR output."""
    langs = list(dict.fromkeys(target_langs or ["sr"]))
    if "sr" in langs and "mk" in langs:
        return ["sr", "mk"]
    return langs


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
            "Локална анализа на изворите (користи ја при споредба на извори и непознати детали):\n<source_comparison>"
        )
        footer = "</source_comparison>"
    else:
        header = "Lokalna analiza izvora (koristi pri poređenju izvora i nepotvrđenim detaljima):\n<source_comparison>"
        footer = "</source_comparison>"
    return f"{header}\n" + "\n".join(f"- {line}" for line in lines) + f"\n{footer}"


def _fetch_synthesis_history_context(cluster_id, lang="sr", article_rows=None):
    try:
        from core.config import HISTORY_SEMANTIC_THRESHOLD
        from core.embeddings import get_cluster_embedding, local_distance

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
            (
                cluster_id,
                lang,
                cluster_id,
                current_vec_str,
                local_distance(HISTORY_SEMANTIC_THRESHOLD),
                current_vec_str,
            ),
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


def _build_cluster_synthesis_prompt(
    article_rows, lang="sr", history_context="", legacy_summary="", source_comparison=""
):
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
