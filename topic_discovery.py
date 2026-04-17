import logging
import datetime
import json
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from database import db_manager as db
from embeddings import generate_embedding
from local_nlp import extract_cluster_tags_locally, summarize_locally

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
        # Enhanced query to calculate source velocity (sources in last 3 hours)
        unassigned_clusters = db.execute("""
            SELECT DISTINCT a.cluster_id, 
                   AVG(a.embedding) as avg_embedding,
                   MAX(a.created_at) as latest_activity,
                   COUNT(DISTINCT a.source) as source_count,
                   COUNT(DISTINCT CASE WHEN a.created_at >= NOW() - INTERVAL '3 hours' THEN a.source END) as velocity,
                   ARRAY_AGG(DISTINCT a.title) as titles,
                   ARRAY_AGG(DISTINCT a.source) as sources
            FROM articles a
            LEFT JOIN storyline_clusters sc ON a.cluster_id = sc.cluster_id
            WHERE sc.storyline_id IS NULL
              AND a.embedding IS NOT NULL
              AND a.created_at >= NOW() - %s * INTERVAL '1 hour'
            GROUP BY a.cluster_id
            HAVING COUNT(DISTINCT a.source) >= 2
            ORDER BY velocity DESC, latest_activity DESC
        """, (lookback_hours,))

        if not unassigned_clusters:
            log.info("No unassigned clusters found for discovery.")
            return

        for cluster in unassigned_clusters:
            self._process_cluster(cluster)

    def _process_cluster(self, cluster: Dict[str, Any]):
        cid = cluster['cluster_id']
        emb = cluster['avg_embedding']
        velocity = cluster.get('velocity', 0)
        
        # 2. Try to find an existing storyline that is semantically close
        # Stricter lookback for matching (3 days) to keep stories focused
        best_storyline = db.execute_one("""
            SELECT s.id, s.title, 
                   (SELECT AVG(a.embedding) 
                    FROM articles a 
                    JOIN storyline_clusters sc2 ON a.cluster_id = sc2.cluster_id 
                    WHERE sc2.storyline_id = s.id) <=> %s::vector as distance
            FROM storylines s
            WHERE s.is_active = TRUE
              AND s.last_activity >= NOW() - INTERVAL '3 days'
            ORDER BY distance ASC
            LIMIT 1
        """, (emb,))

        if best_storyline and float(best_storyline['distance']) < STORYLINE_LINK_THRESHOLD:
            sid = best_storyline['id']
            log.info(f"Linking cluster {cid} to existing storyline: {best_storyline['title']} (velocity: {velocity})")
            
            db.execute(
                "INSERT INTO storyline_clusters (storyline_id, cluster_id, relevance_score) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (sid, cid, 1.0 - float(best_storyline['distance'])),
                fetch=False
            )
            # Update storyline status based on new activity
            db.execute(
                "UPDATE storylines SET last_activity = NOW(), is_active = TRUE WHERE id = %s",
                (sid,), fetch=False
            )
        else:
            # 3. Create a new storyline if it has sufficient momentum
            if cluster['source_count'] >= 3 or velocity >= 2:
                self._create_new_storyline(cluster)

    def _create_new_storyline(self, cluster: Dict[str, Any]):
        cid = cluster['cluster_id']
        titles = cluster['titles']
        
        # Generate a title for the storyline using local NLP
        # We take the most common terms/tags from the cluster
        tags = extract_cluster_tags_locally(titles, top_n=3)
        if not tags:
            # Fallback to the lead title if no tags
            story_title = titles[0][:100]
        else:
            story_title = " ".join(tags)

        # Basic slugification
        slug = re.sub(r'[^a-z0-9а-я]', '-', story_title.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        slug = f"{slug}-{cid[:8]}" # Ensure uniqueness

        log.info(f"Creating new storyline: {story_title}")
        
        try:
            res = db.execute(
                """INSERT INTO storylines (title, slug, last_activity, metadata) 
                   VALUES (%s, %s, NOW(), %s) RETURNING id""",
                (story_title, slug, json.dumps({"origin_cluster": cid})),
            )
            if res:
                sid = res[0]['id']
                db.execute(
                    "INSERT INTO storyline_clusters (storyline_id, cluster_id, relevance_score) VALUES (%s, %s, %s)",
                    (sid, cid, 1.0),
                    fetch=False
                )
        except Exception as e:
            log.error(f"Failed to create storyline: {e}")

    def refresh_storyline_metadata(self):
        """
        Periodically update summaries and titles for active storylines.
        """
        active_storylines = db.execute("SELECT id, title FROM storylines WHERE is_active = TRUE ORDER BY last_activity DESC LIMIT 20")
        
        for s in active_storylines:
            sid = s['id']
            # Get all titles in this storyline
            rows = db.execute("""
                SELECT a.title, a.description 
                FROM articles a
                JOIN storyline_clusters sc ON a.cluster_id = sc.cluster_id
                WHERE sc.storyline_id = %s
            """, (sid,))
            
            if not rows: continue
            
            # Use local NLP to generate a brief summary of the storyline so far
            combined_text = ". ".join([f"{r['title']}. {r.get('description','')}" for r in rows[:10]])
            story_summary = summarize_locally(combined_text, sentence_count=2)
            
            db.execute(
                "UPDATE storylines SET summary = %s WHERE id = %s",
                (story_summary, sid), fetch=False
            )

discovery_engine = StoryDiscoveryEngine()
