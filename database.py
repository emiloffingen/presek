import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool
import datetime
import logging
import os
import json

log = logging.getLogger("presek")

def _load_env():
    """Fallback: manually load .env file if not set in process environment."""
    if os.environ.get("DATABASE_URL"): return
    try:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        parts = line.strip().split('=', 1)
                        if len(parts) == 2:
                            k, v = parts
                            os.environ[k] = v.strip('"').strip("'")
    except Exception as e:
        log.warning(f"Could not manual-load .env: {e}")

_load_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")

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
        try:
            self._pool = ThreadedConnectionPool(
                minconn=5,
                maxconn=50,
                dsn=DATABASE_URL
            )
            log.info("Presek 4.0: Database connection pool initialized.")
        except Exception as e:
            log.error(f"Failed to initialize database connection pool: {e}")
            self._pool = None

    def get_conn(self):
        if not self._pool:
            return psycopg2.connect(DATABASE_URL)
        return self._pool.getconn()

    def put_conn(self, conn):
        if self._pool:
            try:
                self._pool.putconn(conn)
            except: pass
        else:
            conn.close()

    def execute(self, sql, params=None, fetch=True):
        """Standardized query execution with automatic connection release."""
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

    # --- High-Level DAL Methods ---

    def get_articles_by_ids(self, ids):
        return self.execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (ids,))

    def get_articles_by_country(self, country, limit=200, sub=None, topic=None, sentiment=None):
        sql = "SELECT * FROM articles WHERE 1=1"
        params = []
        if country and country != '🇲🇰':
            sql += " AND country = %s"; params.append(country)
        # If country is 🇲🇰, we show everything that isn't another country flag
        # but for simplicity, we allow 🇲🇰 to match directly too
        elif country == '🇲🇰':
            sql += " AND (country = '🇲🇰' OR country IS NULL OR country = '')"
        if sub:
            sql += " AND subcategory = %s"; params.append(sub)
        if topic:
            sql += " AND topic = %s"; params.append(topic)
        if sentiment:
            sql += " AND summary LIKE %s"; params.append(f"%{sentiment}%")
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        return self.execute(sql, tuple(params))

    def get_personalized_articles(self, follow_sources, follow_topics, limit=200):
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

    def search_articles(self, q, limit=100):
        sql = """
            SELECT *, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('simple', %s)
            ORDER BY rank DESC, created_at DESC
            LIMIT %s
        """
        return self.execute(sql, (q, q, limit))

    def get_synthesis_ids(self, cluster_ids):
        if not cluster_ids: return []
        rows = self.execute("SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)", (cluster_ids,))
        return [r["cluster_id"] for r in rows]

    def get_db_size(self):
        db_name = DATABASE_URL.split('/')[-1].split('?')[0]
        row = self.execute_one("SELECT pg_database_size(%s)", (db_name,))
        if row:
            size_bytes = list(row.values())[0]
            return round(size_bytes / (1024 * 1024), 2)
        return 0.0

    def get_stats(self):
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

    def init_schema(self):
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute("""CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY, cluster_id TEXT NOT NULL, source TEXT NOT NULL, link TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL, original_title TEXT DEFAULT '', description TEXT DEFAULT '', summary TEXT,
                    category TEXT, subcategory TEXT DEFAULT '', topic TEXT DEFAULT 'Вести', country TEXT DEFAULT '🇲🇰',
                    created_at TIMESTAMP NOT NULL, image_url TEXT, clicks INTEGER DEFAULT 0, original_description TEXT DEFAULT '',
                    is_translated INTEGER DEFAULT 0, embedding vector(3072), search_vector tsvector
                )""")
                cur.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (cluster_id TEXT PRIMARY KEY, summary TEXT, perspectives JSONB DEFAULT '[]', created_at TIMESTAMP)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS cluster_metadata (cluster_id TEXT PRIMARY KEY, tags TEXT[], topics TEXT[], updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS cluster_entities (cluster_id TEXT, entity_name TEXT, entity_type TEXT, PRIMARY KEY (cluster_id, entity_name))""")
                cur.execute("""CREATE TABLE IF NOT EXISTS reactions (cluster_id TEXT, emoji TEXT, count INTEGER DEFAULT 1, PRIMARY KEY (cluster_id, emoji))""")
                cur.execute("""CREATE TABLE IF NOT EXISTS daily_briefings (date DATE PRIMARY KEY, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS subscribers (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING GIN (search_vector)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_embedding ON articles USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
                conn.commit()
        finally:
            self.put_conn(conn)

# --- Legacy Compatibility Wrapper ---

class DBWrapper:
    """Wraps a connection to support .cursor(), .execute(), .fetchone(), .fetchall(), and .close() for legacy code."""
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.get_conn()
    def cursor(self):
        return self.conn.cursor(cursor_factory=DictCursor)
    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur
    def commit(self):
        self.conn.commit()
    def rollback(self):
        self.conn.rollback()
    def close(self):
        self.manager.put_conn(self.conn)
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()

db_manager = DatabaseManager()

def get_db(): return DBWrapper(db_manager)
def get_db_size(): return db_manager.get_db_size()
def init_db(): db_manager.init_schema()
def prune_db(): db_manager.execute("DELETE FROM articles WHERE created_at < NOW() - INTERVAL '14 days'", fetch=False)
