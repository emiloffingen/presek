#!/usr/bin/env python3
"""Copy cluster_summaries rows from a mistaken replica write DB into the primary."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value
    return values


def main() -> int:
    import psycopg
    from psycopg.types.json import Json

    env_path = os.environ.get("ENV_FILE", "/home/emiloffingen/presek-runtime/shared/.env")
    env = _load_env(env_path)
    primary_url = env.get("DATABASE_URL", "")
    replica_url = env.get("DATABASE_READ_REPLICA_URL") or env.get("DATABASE_REPLICA_URL", "")
    if not primary_url or not replica_url:
        print("DATABASE_URL and DATABASE_READ_REPLICA_URL are required in env file.")
        return 1
    if primary_url == replica_url:
        print("Primary and replica URLs are identical; nothing to sync.")
        return 0

    columns = [
        "cluster_id",
        "lang",
        "summary",
        "perspectives",
        "generated_article",
        "synthetic_headline",
        "synthetic_standfirst",
        "created_at",
        "sentiment",
        "tone_analysis",
        "verification_report",
        "quote",
        "centroid",
        "citation_sources",
        "key_facts",
        "analyst_entities",
        "pulse_score",
        "pluralism_score",
        "narrative_diversity",
        "storyline_narrative",
        "generation_provider",
        "generation_model",
        "quality_score",
        "fallback_reason",
    ]
    json_columns = {
        "perspectives",
        "sentiment",
        "tone_analysis",
        "verification_report",
        "citation_sources",
        "key_facts",
        "analyst_entities",
        "narrative_diversity",
    }

    def _adapt_row(row: tuple) -> tuple:
        adapted = []
        for col, value in zip(columns, row, strict=True):
            if col in json_columns and value is not None:
                adapted.append(Json(value))
            else:
                adapted.append(value)
        return tuple(adapted)

    with psycopg.connect(replica_url) as replica_conn, psycopg.connect(primary_url) as primary_conn:
        with replica_conn.cursor() as replica_cur, primary_conn.cursor() as primary_cur:
            primary_cur.execute("SELECT COALESCE(MAX(created_at), '1970-01-01'::timestamp) FROM cluster_summaries")
            cutoff = primary_cur.fetchone()[0]
            replica_cur.execute(
                f"""
                SELECT {", ".join(columns)}
                FROM cluster_summaries
                WHERE created_at > %s
                ORDER BY created_at ASC
                """,
                (cutoff,),
            )
            rows = replica_cur.fetchall()
            if not rows:
                print("No newer summaries found on replica.")
                return 0

            placeholders = ", ".join(["%s"] * len(columns))
            updates = ", ".join(
                f"{col} = EXCLUDED.{col}"
                for col in columns
                if col not in ("cluster_id", "lang")
            )
            sql = f"""
                INSERT INTO cluster_summaries ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT (cluster_id, lang) DO UPDATE SET {updates}
            """
            synced = 0
            for row in rows:
                primary_cur.execute(sql, _adapt_row(row))
                synced += 1
            primary_conn.commit()
            print(f"Synced {synced} cluster_summaries rows from replica to primary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
