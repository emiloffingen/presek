import asyncio
import logging
import re
from database import db_manager as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.analyst")


def extract_local_facts(texts):
    """Zero-token fact extraction using regex and position."""
    facts = []
    # Patterns for numbers, percentages, dates
    patterns = [
        r"\d+(?:\.\d+)?%",  # Percentages
        r"\d+(?:\.\d+)?\s*(?:милиони|милијарди|евра|денари|USD|EUR)",  # Money
        r"(?:во|на)\s+\d{1,2}\s+(?:јануари|февруари|март|април|мај|јуни|јули|август|септември|октомври|ноември|декември)",  # Dates
    ]

    for text in texts:
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for s in sentences:
            if any(re.search(p, s) for p in patterns):
                if len(s) > 30 and len(s) < 200:
                    facts.append(s.strip())

    return list(set(facts))[:5]


def extract_local_perspectives(texts):
    """Zero-token quote/perspective extraction."""
    perspectives = []
    # Journalistic attribution verbs
    verbs = ["изјави", "рече", "додаде", "посочи", "истакна", "нагласи", "вели"]

    for text in texts:
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for s in sentences:
            if any(v in s.lower() for v in verbs):
                if '"' in s or "„" in s or "“" in s or ":" in s:
                    perspectives.append(s.strip())

    return list(set(perspectives))[:5]


async def run_analyst_prototype():
    print("\n--- Presek Zero-Token Local Analyst Prototype ---")

    # 1. Get a cluster with full content
    row = db.execute_one(
        """
        SELECT cluster_id, MIN(title) as title
        FROM articles 
        WHERE full_content IS NOT NULL AND LENGTH(full_content) > 500
        GROUP BY cluster_id LIMIT 1
    """
    )

    if not row:
        print("No clusters with full content found. Please run ingestion first.")
        return

    cid = row["cluster_id"]
    print(f"Analyzing Cluster: {row['title']}\n")

    # 2. Fetch full contents
    arts = db.execute(
        "SELECT full_content, source FROM articles WHERE cluster_id = %s AND full_content IS NOT NULL",
        (cid,),
    )
    contents = [a["full_content"] for a in arts]

    # 3. Process
    print("📊 [MODE: FACTS]")
    facts = extract_local_facts(contents)
    for f in facts:
        print(f"  • {f}")

    print("\n⚖️ [MODE: PERSPECTIVES]")
    quotes = extract_local_perspectives(contents)
    for q in quotes:
        print(f"  • {q}")

    print("\n🔍 [MODE: CONTEXT]")
    # We reuse our semantic history for context
    # (Simplified for prototype)
    print("  • Системот користи pgvector за поврзување со минати настани.")


if __name__ == "__main__":
    asyncio.run(run_analyst_prototype())
