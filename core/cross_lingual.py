"""Cross-lingual storyline counterpart lookups."""

from __future__ import annotations

from core.database import db_manager as db


async def get_cross_lingual_counterparts(
    cluster_id: str, lang: str, limit: int = 4
) -> list[dict]:
    other_lang = "mk" if lang == "sr" else "sr"
    rows = (
        await db.async_execute(
            """
        SELECT DISTINCT ON (sc2.cluster_id)
            sc2.cluster_id,
            cs.lang,
            cs.synthetic_headline,
            s.title AS storyline_title,
            sc2.relevance_score
        FROM storyline_clusters_v2 sc1
        JOIN storylines_v2 s ON s.id = sc1.storyline_id
        JOIN storyline_clusters_v2 sc2
          ON sc2.storyline_id = s.id
         AND sc2.cluster_id != sc1.cluster_id
        LEFT JOIN cluster_summaries cs
          ON cs.cluster_id = sc2.cluster_id
         AND cs.lang = %s
        WHERE sc1.cluster_id = %s
          AND COALESCE((s.metadata->>'is_cross_lingual')::boolean, false) = true
          AND cs.synthetic_headline IS NOT NULL
        ORDER BY sc2.cluster_id, sc2.relevance_score DESC NULLS LAST
        LIMIT %s
        """,
            (other_lang, cluster_id, limit),
            read_only=True,
        )
        or []
    )

    return [
        {
            "cluster_id": row["cluster_id"],
            "lang": row.get("lang") or other_lang,
            "headline": row.get("synthetic_headline") or "",
            "storyline_title": row.get("storyline_title") or "",
            "relevance_score": float(row.get("relevance_score") or 0),
        }
        for row in rows
        if row.get("cluster_id")
    ]
