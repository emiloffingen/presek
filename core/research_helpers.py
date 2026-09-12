"""Shared research mode constants and cluster context builders."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException

from core.database import db_manager as db

log = logging.getLogger("presek")

RESEARCH_MODE_QUERIES = {
    "sr": {
        "facts": (
            "Izvuci najvažnije brojke, datume, činjenice i vremenski okvir iz ove priče. "
            "Ne dodaj brojke koje ne postoje u kontekstu."
        ),
        "perspectives": (
            "Identifikuj ključne aktere, njihove stavove, izjave i različite uglove u priči. "
            "Ne izmišljaj izjave koje nisu u kontekstu."
        ),
        "context": (
            "Objasni širi kontekst, prethodna povezana dešavanja i moguće posledice ove priče. "
            "Jasno odvoji ono što je u izvorima od analitičkog okvira."
        ),
    },
    "mk": {
        "facts": (
            "Izvleci im najvaznite brojki, datumi, fakti i vremenska ramka od ova prica. "
            "Ne dodavaj brojki sto ne postojat vo kontekstot."
        ),
        "perspectives": (
            "Identifikuvaj im klucnite akteri, nivnite stavovi, izjavi i razlicnite agli vo prikaznata. "
            "Ne izmisluvaj izjavi sto ne se vo kontekstot."
        ),
        "context": (
            "Objasni ga posirokiot kontekst, prethodnite povrzani slucuvanja i moznite posledice od ova prica. "
            "Jasno oddeli sto e vo izvorite od analitickata ramka."
        ),
    },
}

RESEARCH_MODE_LABELS = {
    "facts": "Fakti i podatoci",
    "perspectives": "Perspektivi i izjavi",
    "context": "Kontekstualna ramka",
    "custom": "odgovor na istrazuvanjeto",
}

# Static focus plan per mode — avoids an extra LLM round-trip before report generation.
RESEARCH_MODE_PLAN = {
    "sr": {
        "facts": "1. Ključne brojke i datumi\n2. Proverene činjenice\n3. Vremenski okvir",
        "perspectives": "1. Ključni akteri i stavovi\n2. Različiti uglovi\n3. Konflikti između izvora",
        "context": "1. Širi kontekst\n2. Prethodni događaji\n3. Moguće posledice",
        "custom": "1. Direktan odgovor na pitanje\n2. Podržavajući kontekst\n3. Nepoznato ili neprovereno",
    },
    "mk": {
        "facts": "1. Klucni brojki i datumi\n2. Provereni fakti\n3. Vremenska ramka",
        "perspectives": "1. Klucni akteri i stavovi\n2. Razlicni agli\n3. Konflikti megju izvorite",
        "context": "1. Posirok kontekst\n2. Prethodni nastani\n3. Mozni posledici",
        "custom": "1. Direkten odgovor na prasanjeto\n2. Poddrzuvacki kontekst\n3. Nepoznato ili neprovereno",
    },
}


async def build_gemma_research_context(cluster_id: str, mode: str = "custom", query: str = "") -> tuple[str, list[str]]:
    articles = await db.async_execute(
        """
        SELECT title, full_content, source, embedding, created_at
        FROM articles
        WHERE cluster_id = %s
        ORDER BY COALESCE(ingested_at, created_at) DESC
        LIMIT 20
    """,
        (cluster_id,),
    )

    if not articles:
        raise HTTPException(status_code=404, detail="klaster nije pronadjen")

    summary_row = await db.async_execute_one(
        """
        SELECT summary, generated_article, verification_report, perspectives
        FROM cluster_summaries
        WHERE cluster_id = %s
    """,
        (cluster_id,),
    )

    parts = []
    if summary_row:
        if summary_row.get("summary"):
            parts.append(f"UREDNICKO rezime:\n{summary_row['summary']}")
        if summary_row.get("generated_article"):
            parts.append(f"SINTEZA:\n{summary_row['generated_article']}")
        if summary_row.get("verification_report"):
            try:
                vr = (
                    json.loads(summary_row["verification_report"])
                    if isinstance(summary_row["verification_report"], str)
                    else summary_row["verification_report"]
                )
                parts.append(f"PROVERKA NA FAKTI (Sistemska analiza):\n{json.dumps(vr, ensure_ascii=False, indent=2)}")
            except Exception as e:
                log.debug(f"Failed to parse verification_report JSON: {e}")
        if summary_row.get("perspectives"):
            try:
                pers = (
                    json.loads(summary_row["perspectives"])
                    if isinstance(summary_row["perspectives"], str)
                    else summary_row["perspectives"]
                )
                parts.append(
                    f"MEDIUMSKI PERSPEKTIVI (Sistemska analiza):\n{json.dumps(pers, ensure_ascii=False, indent=2)}"
                )
            except Exception as e:
                log.debug(f"Failed to parse perspectives JSON: {e}")

    sources = []
    for article in articles:
        source = str(article.get("source") or "Nepoznat izvor").strip()
        if source and source not in sources:
            sources.append(source)
        text = article.get("full_content") or article.get("title") or ""
        parts.append(f"--- izvor: {source} ({article['created_at'].strftime('%H:%M %d.%m.%Y')}) ---\n{text}")

    if mode == "context":
        try:
            import numpy as np

            vecs = [
                (json.loads(a["embedding"]) if isinstance(a.get("embedding"), str) else list(a["embedding"]))
                for a in articles
                if a.get("embedding")
            ]
            if vecs:
                avg_vec = np.mean(vecs, axis=0).tolist()
                vec_str = "[" + ",".join(map(str, avg_vec)) + "]"
                past_events = await db.async_execute(
                    """
                    SELECT title, created_at
                    FROM articles
                    WHERE embedding IS NOT NULL AND cluster_id != %s
                      AND created_at < NOW() - INTERVAL '24 hours'
                    ORDER BY (embedding <=> %s::vector) ASC
                    LIMIT 10
                """,
                    (cluster_id, vec_str),
                )
                if past_events:
                    history_list = "\n".join(
                        [f"- {p['title']} ({p['created_at'].strftime('%d.%m.%Y')})" for p in past_events]
                    )
                    parts.append(f"POVRZANI PRETHODNI NASTANI OD BAZATA:\n{history_list}")
        except Exception as e:
            log.warning(f"Failed to fetch Gemma research history context: {e}")

    return "\n\n".join(parts)[:45000], sources
