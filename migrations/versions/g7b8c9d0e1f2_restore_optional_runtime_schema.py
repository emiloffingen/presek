"""restore optional runtime tables and vector columns for the MK deployment

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from typing import Sequence, Union

from alembic import op


revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding vector(384)")
    op.execute("ALTER TABLE cluster_metadata ADD COLUMN IF NOT EXISTS centroid vector(384)")
    op.execute("CREATE TABLE IF NOT EXISTS synced_reader_profiles (sync_token TEXT PRIMARY KEY, profile_data JSONB DEFAULT '{}'::jsonb, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    op.execute("CREATE TABLE IF NOT EXISTS synced_delivery_subscriptions (sync_token TEXT PRIMARY KEY REFERENCES synced_reader_profiles(sync_token) ON DELETE CASCADE, channel TEXT DEFAULT 'ntfy', target TEXT DEFAULT '', morning_briefing BOOLEAN DEFAULT TRUE, weekly_digest BOOLEAN DEFAULT FALSE, breaking_topics BOOLEAN DEFAULT FALSE, breaking_sources BOOLEAN DEFAULT FALSE, is_active BOOLEAN DEFAULT FALSE, last_morning_sent_at TIMESTAMP, last_weekly_sent_at TIMESTAMP, last_breaking_sent_at TIMESTAMP, last_alert_cluster_ids JSONB DEFAULT '[]'::jsonb, last_alert_context JSONB DEFAULT '{}'::jsonb, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    op.execute("CREATE TABLE IF NOT EXISTS knowledge_entities (name TEXT PRIMARY KEY, type TEXT, total_mentions INTEGER DEFAULT 1, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, sentiment_score REAL DEFAULT 0, image_url TEXT, metadata JSONB DEFAULT '{}')")
    op.execute("CREATE TABLE IF NOT EXISTS knowledge_relationships (entity_a TEXT REFERENCES knowledge_entities(name), entity_b TEXT REFERENCES knowledge_entities(name), weight INTEGER DEFAULT 1, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (entity_a, entity_b))")
    op.execute("CREATE TABLE IF NOT EXISTS entity_mentions_daily (entity_name TEXT REFERENCES knowledge_entities(name) ON DELETE CASCADE, cluster_id TEXT NOT NULL, day DATE DEFAULT CURRENT_DATE, PRIMARY KEY (entity_name, cluster_id, day))")
    op.execute("CREATE TABLE IF NOT EXISTS cluster_entities (cluster_id TEXT, entity_name TEXT, entity_type TEXT, mentions INTEGER DEFAULT 1, PRIMARY KEY (cluster_id, entity_name))")
    op.execute("CREATE TABLE IF NOT EXISTS daily_briefings (date DATE PRIMARY KEY, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    op.execute("CREATE TABLE IF NOT EXISTS storylines_v2 (id SERIAL PRIMARY KEY, title TEXT NOT NULL, slug TEXT UNIQUE, summary TEXT, status TEXT DEFAULT 'active', last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata JSONB DEFAULT '{}'::jsonb, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    op.execute("CREATE TABLE IF NOT EXISTS storyline_clusters_v2 (storyline_id INTEGER REFERENCES storylines_v2(id) ON DELETE CASCADE, cluster_id TEXT NOT NULL, relevance_score REAL DEFAULT 1.0, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (storyline_id, cluster_id))")
    op.execute("CREATE TABLE IF NOT EXISTS saved_insights (id SERIAL PRIMARY KEY, user_id VARCHAR(64) NOT NULL, cluster_id VARCHAR(64) NOT NULL, title VARCHAR(255) NOT NULL, report TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")


def downgrade() -> None:
    raise NotImplementedError("Runtime compatibility tables are retained during downgrade")
