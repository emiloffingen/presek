"""baseline_schema

Revision ID: b251aec55d2e
Revises: 438101a6575f
Create Date: 2026-04-26 17:54:15.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b251aec55d2e'
down_revision: Union[str, Sequence[str], None] = '438101a6575f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Articles Table
    op.execute("""CREATE TABLE IF NOT EXISTS articles (
        id SERIAL PRIMARY KEY, 
        cluster_id TEXT NOT NULL, 
        source TEXT NOT NULL, 
        link TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL, 
        original_title TEXT DEFAULT '', 
        description TEXT DEFAULT '', 
        summary TEXT,
        category TEXT, 
        subcategory TEXT DEFAULT '', 
        topic TEXT DEFAULT 'Вести',
        country TEXT DEFAULT 'MK',
        created_at TIMESTAMP NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        image_url TEXT, 
        local_image_path TEXT,
        clicks INTEGER DEFAULT 0, 
        original_description TEXT DEFAULT '',
        is_translated INTEGER DEFAULT 0, 
        is_fact_check BOOLEAN DEFAULT FALSE,
        embedding vector(384),
        search_vector tsvector
    )""")

    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS local_image_path TEXT")

    # Handle vector dimension change if table already existed (migration support)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='articles' AND column_name='embedding'
            ) THEN
                IF (SELECT atttypmod FROM pg_attribute 
                    WHERE attrelid = 'articles'::regclass AND attname = 'embedding') != 384 THEN
                    ALTER TABLE articles DROP COLUMN embedding;
                    ALTER TABLE articles ADD COLUMN embedding vector(384);
                END IF;
            END IF;
        END $$;
    """)

    # 3. Cluster Summaries & History
    op.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
        cluster_id TEXT PRIMARY KEY, 
        summary TEXT, 
        generated_article TEXT,
        synthetic_headline TEXT,
        synthetic_standfirst TEXT,
        perspectives JSONB DEFAULT '[]', 
        sentiment JSONB DEFAULT '{}',
        tone_analysis JSONB DEFAULT '{}',
        verification_report JSONB,
        quote TEXT,
        citation_sources JSONB DEFAULT '[]',
        created_at TIMESTAMP
    )""")
    
    op.execute("""CREATE TABLE IF NOT EXISTS cluster_summary_history (
        id SERIAL PRIMARY KEY,
        cluster_id TEXT NOT NULL,
        summary TEXT,
        generated_article TEXT,
        synthetic_headline TEXT,
        synthetic_standfirst TEXT,
        perspectives JSONB DEFAULT '[]',
        tone_analysis JSONB DEFAULT '{}',
        citation_sources JSONB DEFAULT '[]',
        verification_report JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # 4. Metadata & Entities
    op.execute("""CREATE TABLE IF NOT EXISTS cluster_metadata (
        cluster_id TEXT PRIMARY KEY, 
        tags TEXT[], 
        topics TEXT[], 
        representative_image TEXT,
        dominant_color TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    op.execute("""CREATE TABLE IF NOT EXISTS cluster_entities (
        cluster_id TEXT, 
        entity_name TEXT, 
        entity_type TEXT, 
        PRIMARY KEY (cluster_id, entity_name)
    )""")

    # 5. Engagement & Support
    op.execute("""CREATE TABLE IF NOT EXISTS reactions (
        cluster_id TEXT, 
        emoji TEXT, 
        count INTEGER DEFAULT 1, 
        PRIMARY KEY (cluster_id, emoji)
    )""")

    op.execute("""CREATE TABLE IF NOT EXISTS daily_briefings (
        date DATE PRIMARY KEY, 
        content TEXT, 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    op.execute("""CREATE TABLE IF NOT EXISTS subscribers (
        id SERIAL PRIMARY KEY, 
        email TEXT UNIQUE NOT NULL, 
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # 6. Reader Profiles & Subscriptions
    op.execute("""CREATE TABLE IF NOT EXISTS synced_reader_profiles (
        sync_token TEXT PRIMARY KEY,
        profile_data JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    op.execute("""CREATE TABLE IF NOT EXISTS synced_delivery_subscriptions (
        sync_token TEXT PRIMARY KEY REFERENCES synced_reader_profiles(sync_token) ON DELETE CASCADE,
        channel TEXT DEFAULT 'ntfy',
        target TEXT DEFAULT '',
        morning_briefing BOOLEAN DEFAULT TRUE,
        weekly_digest BOOLEAN DEFAULT FALSE,
        breaking_topics BOOLEAN DEFAULT FALSE,
        breaking_sources BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT FALSE,
        last_morning_sent_at TIMESTAMP,
        last_weekly_sent_at TIMESTAMP,
        last_breaking_sent_at TIMESTAMP,
        last_alert_cluster_ids JSONB DEFAULT '[]'::jsonb,
        last_alert_context JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # 7. Tracking & Logs
    op.execute("""CREATE TABLE IF NOT EXISTS delivery_tracking_events (
        id SERIAL PRIMARY KEY,
        sync_token TEXT REFERENCES synced_reader_profiles(sync_token) ON DELETE CASCADE,
        parent_event_id INTEGER REFERENCES delivery_tracking_events(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        delivery_kind TEXT NOT NULL,
        channel TEXT DEFAULT 'ntfy',
        target TEXT DEFAULT '',
        cluster_id TEXT,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    op.execute("""CREATE TABLE IF NOT EXISTS suggestion_surface_events (
        id SERIAL PRIMARY KEY,
        sync_token TEXT REFERENCES synced_reader_profiles(sync_token) ON DELETE SET NULL,
        client_id TEXT,
        surface TEXT NOT NULL,
        suggestion_kind TEXT,
        event_type TEXT NOT NULL,
        value TEXT DEFAULT '',
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    op.execute("""CREATE TABLE IF NOT EXISTS failed_tasks (
        id SERIAL PRIMARY KEY,
        task_name TEXT NOT NULL,
        args JSONB DEFAULT '[]'::jsonb,
        kwargs JSONB DEFAULT '{}'::jsonb,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    op.execute("""
        CREATE TABLE IF NOT EXISTS entity_knowledge (
            entity_name TEXT PRIMARY KEY,
            bio_summary TEXT DEFAULT '',
            importance_score REAL DEFAULT 0,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            category TEXT DEFAULT '',
            metadata JSONB DEFAULT '{}'::jsonb
        )
    """)

    # 8. Sources
    op.execute("""CREATE TABLE IF NOT EXISTS sources (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        url TEXT NOT NULL,
        country TEXT DEFAULT 'MK',
        category TEXT DEFAULT 'Локални',
        credibility FLOAT DEFAULT 1.0,
        is_active BOOLEAN DEFAULT TRUE,
        last_fetched TIMESTAMP,
        fetch_interval INTEGER DEFAULT 300,
        source_limit INTEGER DEFAULT 10,
        pause_mode TEXT,
        pause_reason TEXT,
        paused_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # 9. Knowledge Graph & Storylines
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_entities (
            name TEXT PRIMARY KEY,
            type TEXT,
            total_mentions INTEGER DEFAULT 1,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sentiment_score REAL DEFAULT 0,
            image_url TEXT,
            metadata JSONB DEFAULT '{}'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_relationships (
            entity_a TEXT REFERENCES knowledge_entities(name),
            entity_b TEXT REFERENCES knowledge_entities(name),
            weight INTEGER DEFAULT 1,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (entity_a, entity_b)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS entity_mentions_daily (
            entity_name TEXT REFERENCES knowledge_entities(name) ON DELETE CASCADE,
            cluster_id TEXT NOT NULL,
            day DATE DEFAULT CURRENT_DATE,
            PRIMARY KEY (entity_name, cluster_id, day)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS storylines_v2 (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            slug TEXT UNIQUE,
            summary TEXT,
            status TEXT DEFAULT 'active',
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS storyline_clusters_v2 (
            storyline_id INTEGER REFERENCES storylines_v2(id) ON DELETE CASCADE,
            cluster_id TEXT NOT NULL,
            relevance_score REAL DEFAULT 1.0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (storyline_id, cluster_id)
        )
    """)

    # 10. Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ingested_at ON articles(ingested_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING GIN (search_vector)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_country_created ON articles(country, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_source_created ON articles(source, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_cat_created ON articles(category, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_local_image_path ON articles(local_image_path) WHERE local_image_path IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_embedding ON articles USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cluster_metadata_tags ON cluster_metadata USING GIN (tags)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cluster_summary_history_cid ON cluster_summary_history(cluster_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rel_weight ON knowledge_relationships(weight DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rel_entity_b ON knowledge_relationships(entity_b)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_delivery_tracking_sync_created ON delivery_tracking_events(sync_token, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_delivery_tracking_event_kind_created ON delivery_tracking_events(event_type, delivery_kind, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suggestion_surface_events_created ON suggestion_surface_events(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suggestion_surface_events_surface_kind ON suggestion_surface_events(surface, suggestion_kind, event_type, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suggestion_surface_events_sync_created ON suggestion_surface_events(sync_token, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_failed_tasks_created ON failed_tasks(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_entity_knowledge_last_seen ON entity_knowledge(last_seen DESC)")

    # 11. Triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION articles_search_trigger() RETURNS trigger AS $$
        BEGIN
          new.search_vector :=
            setweight(to_tsvector('simple', coalesce(new.title,'')), 'A') ||
            setweight(to_tsvector('simple', coalesce(new.description,'')), 'B');
          return new;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'tsvectorupdate') THEN
                CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
                ON articles FOR EACH ROW EXECUTE FUNCTION articles_search_trigger();
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    pass
