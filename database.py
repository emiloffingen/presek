import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool
import datetime
import logging
import os
import json

log = logging.getLogger("presek")

class DatabaseManager:
    """Centralized Database Access Layer (DAL) for Presek 4.0."""
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._init_pool()
        return cls._instance

    def _init_pool(self):
        db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")
        try:
            self._pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=30,
                dsn=db_url
            )
            log.info("Presek 4.0: Database connection pool initialized.")
        except Exception as e:
            log.error(f"Failed to initialize database connection pool: {e}")
            self._pool = None

    def get_conn(self):
        if not self._pool:
            db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")
            return psycopg2.connect(db_url)
        return self._pool.getconn()

    def put_conn(self, conn):
        if self._pool:
            self._pool.putconn(conn)
        else:
            conn.close()

    def execute(self, sql, params=None, fetch=True):
        """Standardized query execution with DictCursor and JSON-ready dicts."""
        conn = self.get_conn()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, params)
                if fetch:
                    return [dict(r) for r in cur.fetchall()]
                conn.commit()
                return cur.rowcount
        except Exception as e:
            conn.rollback()
            log.error(f"Presek 4.0 DB Error: {e} | SQL: {sql}")
            raise
        finally:
            self.put_conn(conn)

    def execute_one(self, sql, params=None):
        results = self.execute(sql, params)
        return results[0] if results else None

    # --- High-Level DAL Methods (Stage 1 Refactor) ---

    def get_articles_by_ids(self, ids: list[str]):
        sql = "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC"
        return self.execute(sql, (ids,))

    def get_articles_by_country(self, country: str, limit: int = 200, sub: str = None, topic: str = None, sentiment: str = None):
        sql = "SELECT * FROM articles WHERE 1=1"
        params = []
        if country:
            sql += " AND country = %s"; params.append(country)
        if sub:
            sql += " AND subcategory = %s"; params.append(sub)
        if topic:
            sql += " AND topic = %s"; params.append(topic)
        if sentiment:
            sql += " AND summary LIKE %s"; params.append(f"%{sentiment}%")
        
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        return self.execute(sql, tuple(params))

    def get_personalized_articles(self, follow_sources: list[str], follow_topics: list[str], limit: int = 200):
        sql = "SELECT * FROM articles WHERE 1=1"
        clauses = []
        params = []
        if follow_sources:
            clauses.append("source = ANY(%s)"); params.append(follow_sources)
        if follow_topics:
            clauses.append("topic = ANY(%s)"); params.append(follow_topics)
        
        if clauses:
            sql += " AND (" + " OR ".join(clauses) + ")"
        
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        return self.execute(sql, tuple(params))

    def search_articles(self, q: str, limit: int = 100):
        sql = """
            SELECT *, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('simple', %s)
            ORDER BY rank DESC, created_at DESC
            LIMIT %s
        """
        return self.execute(sql, (q, q, limit))

    def get_synthesis_ids(self, cluster_ids: list[str]):
        if not cluster_ids: return []
        sql = "SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)"
        rows = self.execute(sql, (cluster_ids,))
        return [r["cluster_id"] for r in rows]

    def get_db_size(self):
        db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")
        db_name = db_url.split('/')[-1].split('?')[0]
        row = self.execute_one("SELECT pg_database_size(%s)", (db_name,))
        if row:
            size_bytes = list(row.values())[0]
            return round(size_bytes / (1024 * 1024), 2)
        return 0.0

    def get_stats(self):
        """Returns comprehensive database statistics for health monitoring."""
        total = self.execute_one("SELECT COUNT(*) FROM articles")["count"]
        by_cat = self.execute("SELECT category, COUNT(*) n FROM articles GROUP BY category ORDER BY n DESC")
        by_source = self.execute("SELECT source, COUNT(*) n FROM articles GROUP BY source ORDER BY n DESC")
        recent_24h = self.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '1 day'")["count"]
        summarized = self.execute_one("SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''")["count"]
        
        return {
            "total_articles": total,
            "by_category": by_cat,
            "by_source": by_source,
            "last_24h": recent_24h,
            "summarized": summarized
        }

# Singleton instance
db_manager = DatabaseManager()

# Legacy hooks for minimal breakage during refactor
def get_db(): return db_manager
def get_db_size(): return db_manager.get_db_size()

def init_db():
    """Bootstrap the database schema, extensions, and triggers for Presek 4.0."""
    conn = db_manager.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Articles Table
            cur.execute("""CREATE TABLE IF NOT EXISTS articles (
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
                country TEXT DEFAULT '🇲🇰',
                created_at TIMESTAMP NOT NULL,
                image_url TEXT,
                clicks INTEGER DEFAULT 0,
                original_description TEXT DEFAULT '',
                is_translated INTEGER DEFAULT 0,
                embedding vector(3072),
                search_vector tsvector
            )""")

            # Summary Table
            cur.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
                cluster_id TEXT PRIMARY KEY,
                summary TEXT,
                perspectives JSONB DEFAULT '[]',
                created_at TIMESTAMP
            )""")

            # Metadata & Entities
            cur.execute("""CREATE TABLE IF NOT EXISTS cluster_metadata (cluster_id TEXT PRIMARY KEY, tags TEXT[], topics TEXT[], updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS cluster_entities (cluster_id TEXT, entity_name TEXT, entity_type TEXT, PRIMARY KEY (cluster_id, entity_name))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS reactions (cluster_id TEXT, emoji TEXT, count INTEGER DEFAULT 1, PRIMARY KEY (cluster_id, emoji))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS daily_briefings (date DATE PRIMARY KEY, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS subscribers (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            # Search Triggers
            cur.execute("""
                CREATE OR REPLACE FUNCTION articles_search_trigger() RETURNS trigger AS $$
                begin
                  new.search_vector := setweight(to_tsvector('simple', coalesce(new.title,'')), 'A') || setweight(to_tsvector('simple', coalesce(new.description,'')), 'B');
                  return new;
                end $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'tsvectorupdate') THEN
                        CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE ON articles FOR EACH ROW EXECUTE FUNCTION articles_search_trigger();
                    END IF;
                END $$;
            """)

            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING GIN (search_vector)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_embedding ON articles USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
            
            conn.commit()
            log.info("Presek 4.0: Schema verification complete.")
    finally:
        db_manager.put_conn(conn)

def prune_db():
    """Service method for background maintenance."""
    db_manager.execute("DELETE FROM articles WHERE created_at < NOW() - INTERVAL '14 days'", fetch=False)
