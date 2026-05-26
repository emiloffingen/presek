import json
import logging
import re
from typing import Any, Dict

from core.database import db_manager as db
from nlp.keywords import extract_cluster_tags_locally

log = logging.getLogger("presek.topic_discovery")

# Similarity threshold for linking clusters into a storyline
# Typically higher than standard clustering because we want stronger relationships
STORYLINE_LINK_THRESHOLD = 0.35


class StoryDiscoveryEngine:
    def __init__(self):
        pass

    def run_discovery(self, lookback_hours: int = 48):
        """
        Main loop: Find unassigned clusters and try to link them to existing storylines
        or create new ones.
        """
        log.info(f"Starting Story Discovery (lookback: {lookback_hours}h)")

        # 1. Get recent clusters that aren't already part of a storyline
        # OPTIMIZED: Use cluster_metadata.centroid instead of calculating AVG(embedding) on the fly
        unassigned_clusters = db.execute(
            """
            SELECT DISTINCT a.cluster_id,
                   m.centroid as avg_embedding,
                   MAX(a.created_at) as latest_activity,
                   COUNT(DISTINCT a.source) as source_count,
                   COUNT(DISTINCT CASE WHEN a.created_at >= NOW() - INTERVAL '3 hours' THEN a.source END) as velocity,
                   ARRAY_AGG(DISTINCT a.title) as titles,
                   ARRAY_AGG(DISTINCT a.source) as sources
            FROM articles a
            JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
            LEFT JOIN storyline_clusters_v2 sc ON a.cluster_id = sc.cluster_id
            WHERE sc.storyline_id IS NULL
              AND m.centroid IS NOT NULL
              AND a.created_at >= NOW() - %s * INTERVAL '1 hour'
            GROUP BY a.cluster_id, m.centroid
            HAVING COUNT(DISTINCT a.source) >= 2
            ORDER BY velocity DESC, latest_activity DESC
        """,
            (lookback_hours,),
        )

        if not unassigned_clusters:
            log.info("No unassigned clusters found for discovery.")
            return

        for cluster in unassigned_clusters:
            self._process_cluster(cluster)

    def _process_cluster(self, cluster: Dict[str, Any]):
        cid = cluster["cluster_id"]
        emb = cluster["avg_embedding"]
        velocity = cluster.get("velocity", 0)

        # 2. Try to find an existing storyline that is semantically close
        # OPTIMIZED: Use stored storylines_v2.centroid with HNSW index for O(log n) lookup
        best_storyline = db.execute_one(
            """
            SELECT s.id, s.title, s.metadata,
                   s.centroid <=> %s::vector as distance
            FROM storylines_v2 s
            WHERE s.status = 'active'
              AND s.centroid IS NOT NULL
              AND s.last_activity >= NOW() - INTERVAL '3 days'
            ORDER BY distance ASC
            LIMIT 1
        """,
            (emb,),
        )

        if best_storyline and float(best_storyline["distance"]) < STORYLINE_LINK_THRESHOLD:
            sid = best_storyline["id"]
            log.info(f"Linking cluster {cid} to existing storyline: {best_storyline['title']} (velocity: {velocity})")

            db.execute(
                "INSERT INTO storyline_clusters_v2 (storyline_id, cluster_id, relevance_score) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (sid, cid, 1.0 - float(best_storyline["distance"])),
                fetch=False,
            )
            # Update storyline status and centroid based on new activity
            db.execute(
                "UPDATE storylines_v2 SET last_activity = NOW(), status = 'active' WHERE id = %s",
                (sid,),
                fetch=False,
            )
            # Maintain the storyline centroid
            self._update_storyline_centroid(sid)

            # Update storyline metadata to cross-lingual if languages differ
            try:
                cluster_lang = "mk"
                art_rows = db.execute(
                    "SELECT country FROM articles WHERE cluster_id = %s LIMIT 1",
                    (cid,)
                )
                if art_rows and art_rows[0].get("country") == "RS":
                    cluster_lang = "sr"

                meta = best_storyline.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                
                story_lang = meta.get("lang") or "mk"
                if story_lang != cluster_lang:
                    meta["is_cross_lingual"] = True
                    meta["languages"] = list(set([story_lang, cluster_lang]))
                    db.execute(
                        "UPDATE storylines_v2 SET metadata = %s WHERE id = %s",
                        (json.dumps(meta), sid),
                        fetch=False,
                    )
            except Exception as e:
                log.warning(f"Failed to update cross-lingual metadata for storyline {sid}: {e}")
        else:
            # 3. Create a new storyline if it has sufficient momentum
            if cluster["source_count"] >= 3 or velocity >= 2:
                self._create_new_storyline(cluster)

    def _update_storyline_centroid(self, storyline_id: int):
        """
        Recalculate the storyline centroid as the average of its cluster centroids.
        """
        try:
            db.execute(
                """
                UPDATE storylines_v2
                SET centroid = (
                    SELECT AVG(m.centroid)
                    FROM cluster_metadata m
                    JOIN storyline_clusters_v2 sc ON m.cluster_id = sc.cluster_id
                    WHERE sc.storyline_id = %s
                      AND m.centroid IS NOT NULL
                )
                WHERE id = %s
            """,
                (storyline_id, storyline_id),
                fetch=False,
            )
        except Exception as e:
            log.error(f"Failed to update storyline centroid: {e}")

    def _create_new_storyline(self, cluster: Dict[str, Any]):
        cid = cluster["cluster_id"]
        titles = cluster["titles"]
        emb = cluster["avg_embedding"]

        # Determine dominant language based on articles in this cluster
        lang = "mk"
        try:
            art_rows = db.execute(
                "SELECT country FROM articles WHERE cluster_id = %s LIMIT 1",
                (cid,)
            )
            if art_rows and art_rows[0].get("country") == "RS":
                lang = "sr"
        except Exception as e:
            log.warning(f"Failed to detect dominant language for cluster {cid}: {e}")

        # Phase 4: Use Gemma 2 for Editorial Storyline Titles
        from nlp.local_analyst import analyst

        if lang == "sr":
            system_prompt = (
                "Ti si glavni urednik ozbiljnih srpskih novina. Na osnovu ovih naslova, "
                "generiši jedan kratak, upečatljiv naslov za celu priču (storyline) na srpskom jeziku (latinica). "
                "Vrati samo naslov bez ikakvih navodnika ili objašnjenja."
            )
        else:
            system_prompt = (
                "Ti si glaven urednik na seriozen makedonski vesnik. Vrz osnova na ovie naslovi, "
                "generiraj eden kratok, moćen naslov za celata prica (storyline) na makedonski jazik. "
                "Vrati samo naslov bez nikakvi navodnici ili obrazloženja."
            )

        story_title = analyst.analyze(
            f"Naslovi: {' | '.join(titles[:5])}",
            system_prompt,
            max_tokens=48,
        )

        if not story_title or len(story_title) < 5:
            # Fallback to local logic if Gemma fails
            tags = extract_cluster_tags_locally(titles, top_n=3)
            story_title = " ".join(tags) if tags else titles[0][:100]

        # Basic slugification
        slug = re.sub(r"[^a-z0-9]", "-", story_title.lower())
        slug = re.sub(r"-+", "-", slug).strip("-")
        slug = f"{slug}-{cid[:8]}"  # Ensure uniqueness

        log.info(f"Creating new storyline: {story_title} (lang: {lang})")

        try:
            # Initialize storyline with the first cluster's centroid
            res = db.execute(
                """INSERT INTO storylines_v2 (title, slug, last_activity, centroid, metadata)
                   VALUES (%s, %s, NOW(), %s, %s) RETURNING id""",
                (story_title, slug, emb, json.dumps({"origin_cluster": cid, "lang": lang})),
            )
            if res:
                sid = res[0]["id"]
                db.execute(
                    "INSERT INTO storyline_clusters_v2 (storyline_id, cluster_id, relevance_score) VALUES (%s, %s, %s)",
                    (sid, cid, 1.0),
                    fetch=False,
                )
        except Exception as e:
            log.error(f"Failed to create storyline: {e}")

    def refresh_storyline_metadata(self):
        """
        Periodically update summaries and titles for active storylines using Gemma 2.
        """
        active_storylines = db.execute(
            "SELECT id, title, metadata FROM storylines_v2 WHERE status = 'active' ORDER BY last_activity DESC LIMIT 20"
        )

        from nlp.local_analyst import analyst

        for s in active_storylines:
            sid = s["id"]
            
            # Determine language from metadata
            metadata = s.get("metadata") or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            lang = metadata.get("lang", "mk")
            is_cross_lingual = metadata.get("is_cross_lingual", False)

            # Get all titles and summaries in this storyline
            rows = db.execute(
                """
                SELECT a.title, a.summary
                FROM articles a
                JOIN storyline_clusters_v2 sc ON a.cluster_id = sc.cluster_id
                WHERE sc.storyline_id = %s
                LIMIT 15
            """,
                (sid,),
            )

            if not rows:
                continue

            combined_text = "\n".join([f"• {r['title']}: {r.get('summary','')}" for r in rows])
            
            if is_cross_lingual:
                system_prompt = (
                    "Ti si glavni regionalni urednik za Balkan. Ova priča (storyline) se prati i u srpskim i u makedonskim medijima. "
                    "Na osnovu naslova i rezimea u nastavku, napiši jedan integrisani, uravnotežen regionalni pregled (3-4 rečenice) "
                    "na srpskom jeziku (latinica) i makedonskom jeziku koji objašnjava regionalni kontekst i reakcije u obe zemlje. "
                    "Koristi jasan, neutralan i analitički novinarski stil."
                )
            elif lang == "sr":
                system_prompt = (
                    "Napiši kratak pregled (2-3 rečenice) na srpskom jeziku (latinica) za dosadašnji razvoj "
                    "ove priče na osnovu događaja ispod. Fokusiraj se na glavni narativ."
                )
            else:
                system_prompt = (
                    "Napiši kratok pregled (2-3 rečenice) na makedonski jazik za dosegašniot razvoj "
                    "na ovaa prica vrz osnova na nastanite podolu. Fokusiraj se na glavniot narativ."
                )

            story_summary = analyst.analyze(
                combined_text,
                system_prompt,
                max_tokens=256,
            )

            if story_summary:
                db.execute(
                    "UPDATE storylines_v2 SET summary = %s WHERE id = %s",
                    (story_summary, sid),
                    fetch=False,
                )


discovery_engine = StoryDiscoveryEngine()
