#!/usr/bin/env python3
"""Split a mixed cluster by re-running clustering logic on its articles."""

from __future__ import annotations

import argparse

import core.clustering as clustering
from core.config import CLUSTER_LOOKBACK
from core.database import db_manager as db
from core.embeddings import parse_embedding_value
from nlp.categories import detect_topic


def split_mixed_cluster(cluster_id: str, *, dry_run: bool = False) -> dict:
    articles = db.execute(
        """
        SELECT id, title, description, source, category, topic, country, created_at, embedding, cluster_id
        FROM articles
        WHERE cluster_id = %s
        ORDER BY COALESCE(created_at, ingested_at), id
        """,
        (cluster_id,),
    )
    if not articles:
        return {"cluster_id": cluster_id, "status": "not_found", "updates": []}

    recent_articles = db.execute(
        """
        SELECT title, cluster_id, created_at, category, topic, source
        FROM articles
        WHERE cluster_id != %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (cluster_id, CLUSTER_LOOKBACK),
    ) or []

    updates: list[dict] = []
    touched_clusters = {cluster_id}

    with db.connection() as conn:
        for article in articles:
            title = str(article.get("title") or "").strip()
            description = str(article.get("description") or "")
            category = article.get("category")
            country = str(article.get("country") or "MK")
            lang = "mk" if country == "MK" else "sr"
            detected_topic = detect_topic(title, description=description)
            topic = detected_topic or str(article.get("topic") or "vesti").strip() or "vesti"
            embedding = parse_embedding_value(article.get("embedding"))

            new_cluster_id = clustering.find_or_create_cluster(
                conn,
                title,
                recent_articles,
                embedding=embedding,
                category=category,
                source=article.get("source"),
                topic=topic,
                lang=lang,
                semantic_entities=False,
            )

            old_cluster_id = str(article.get("cluster_id") or "")
            topic_changed = topic != (article.get("topic") or "vesti")
            cluster_changed = new_cluster_id != old_cluster_id

            if cluster_changed or topic_changed:
                updates.append(
                    {
                        "id": article["id"],
                        "title": title,
                        "old_cluster_id": old_cluster_id,
                        "new_cluster_id": new_cluster_id,
                        "old_topic": article.get("topic"),
                        "new_topic": topic,
                    }
                )
                touched_clusters.update({old_cluster_id, new_cluster_id})

            if not dry_run and (cluster_changed or topic_changed):
                db.execute(
                    "UPDATE articles SET cluster_id = %s, topic = %s WHERE id = %s",
                    (new_cluster_id, topic, article["id"]),
                    fetch=False,
                )

            recent_articles.insert(
                0,
                {
                    "title": title,
                    "cluster_id": new_cluster_id,
                    "created_at": article.get("created_at"),
                    "category": category,
                    "topic": topic,
                    "source": article.get("source"),
                },
            )
            if len(recent_articles) > CLUSTER_LOOKBACK:
                recent_articles.pop()

    if dry_run:
        return {"cluster_id": cluster_id, "status": "dry_run", "updates": updates}

    if not updates:
        return {"cluster_id": cluster_id, "status": "unchanged", "updates": []}

    touched = sorted(touched_clusters)
    for table in ("cluster_summaries", "cluster_metadata", "cluster_entities", "reactions"):
        db.execute(f"DELETE FROM {table} WHERE cluster_id = ANY(%s)", (touched,), fetch=False)

    try:
        from tasks.intelligence import auto_summarize_task, extract_entities_task, generate_cluster_metadata_task

        extract_entities_task.apply_async(kwargs={"target_clusters": touched}, countdown=5)
        generate_cluster_metadata_task.apply_async(kwargs={"target_clusters": touched}, countdown=10)
        auto_summarize_task.apply_async(args=(touched,), countdown=20)
    except Exception:
        pass

    return {"cluster_id": cluster_id, "status": "split", "updates": updates, "touched_clusters": touched}


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a mixed cluster using current clustering rules.")
    parser.add_argument("cluster_id", help="Cluster ID to repair")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    args = parser.parse_args()

    result = split_mixed_cluster(args.cluster_id, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
