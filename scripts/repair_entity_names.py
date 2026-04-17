import os
import sys


sys.path.insert(0, os.getcwd())

from database import db_manager as db
from entities import ENTITY_ALIASES, KNOWN_ENTITIES


def merge_knowledge_entity(alias: str, canonical: str) -> None:
    if alias == canonical:
        return

    alias_row = db.execute_one(
        "SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score, metadata FROM knowledge_entities WHERE name = %s",
        (alias,),
    )
    if not alias_row:
        return

    canonical_row = db.execute_one(
        "SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score, metadata FROM knowledge_entities WHERE name = %s",
        (canonical,),
    )

    canonical_type = (canonical_row or {}).get("type") or KNOWN_ENTITIES.get(canonical) or alias_row.get("type")
    total_mentions = int(alias_row.get("total_mentions") or 0) + int((canonical_row or {}).get("total_mentions") or 0)
    sentiment_values = [value for value in [alias_row.get("sentiment_score"), (canonical_row or {}).get("sentiment_score")] if value is not None]
    sentiment_score = sum(sentiment_values) / len(sentiment_values) if sentiment_values else 0
    first_seen = min(value for value in [alias_row.get("first_seen"), (canonical_row or {}).get("first_seen")] if value is not None)
    last_seen = max(value for value in [alias_row.get("last_seen"), (canonical_row or {}).get("last_seen")] if value is not None)

    db.execute(
        """
        INSERT INTO knowledge_entities (name, type, total_mentions, first_seen, last_seen, sentiment_score, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::jsonb, '{}'::jsonb))
        ON CONFLICT (name) DO UPDATE SET
            type = EXCLUDED.type,
            total_mentions = EXCLUDED.total_mentions,
            first_seen = EXCLUDED.first_seen,
            last_seen = EXCLUDED.last_seen,
            sentiment_score = EXCLUDED.sentiment_score,
            metadata = COALESCE(knowledge_entities.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
        """,
        (canonical, canonical_type, total_mentions, first_seen, last_seen, sentiment_score, "{}"),
        fetch=False,
    )

    relationship_rows = db.execute(
        "SELECT entity_a, entity_b, weight, last_seen FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s",
        (alias, alias),
    )
    merged = {}
    for row in relationship_rows:
        left = canonical if row["entity_a"] == alias else row["entity_a"]
        right = canonical if row["entity_b"] == alias else row["entity_b"]
        if left == right:
            continue
        pair = tuple(sorted((left, right)))
        bucket = merged.setdefault(pair, {"weight": 0, "last_seen": row.get("last_seen")})
        bucket["weight"] += int(row.get("weight") or 0)
        if row.get("last_seen") and (bucket["last_seen"] is None or row["last_seen"] > bucket["last_seen"]):
            bucket["last_seen"] = row["last_seen"]

    db.execute("DELETE FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s", (alias, alias), fetch=False)
    for (left, right), payload in merged.items():
        db.execute(
            """
            INSERT INTO knowledge_relationships (entity_a, entity_b, weight, last_seen)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (entity_a, entity_b) DO UPDATE SET
                weight = knowledge_relationships.weight + EXCLUDED.weight,
                last_seen = GREATEST(knowledge_relationships.last_seen, EXCLUDED.last_seen)
            """,
            (left, right, payload["weight"], payload["last_seen"]),
            fetch=False,
        )

    cluster_rows = db.execute("SELECT cluster_id, entity_type FROM cluster_entities WHERE entity_name = %s", (alias,))
    for row in cluster_rows:
        db.execute(
            """
            INSERT INTO cluster_entities (cluster_id, entity_name, entity_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (cluster_id, entity_name) DO UPDATE SET
                entity_type = COALESCE(cluster_entities.entity_type, EXCLUDED.entity_type)
            """,
            (row["cluster_id"], canonical, canonical_type or row.get("entity_type")),
            fetch=False,
        )
    db.execute("DELETE FROM cluster_entities WHERE entity_name = %s", (alias,), fetch=False)
    db.execute("DELETE FROM knowledge_entities WHERE name = %s", (alias,), fetch=False)


def main() -> None:
    repaired = 0
    for alias, canonical in sorted(ENTITY_ALIASES.items(), key=lambda item: (-len(item[0]), item[0])):
        if canonical not in KNOWN_ENTITIES:
            continue
        alias_row = db.execute_one("SELECT name FROM knowledge_entities WHERE name = %s", (alias,))
        cluster_row = db.execute_one("SELECT entity_name FROM cluster_entities WHERE entity_name = %s LIMIT 1", (alias,))
        if not alias_row and not cluster_row:
            continue
        merge_knowledge_entity(alias, canonical)
        repaired += 1
        print(f"merged {alias!r} -> {canonical!r}")
    print(f"repaired_aliases={repaired}")


if __name__ == "__main__":
    main()
