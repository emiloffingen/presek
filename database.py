import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool
import datetime
import logging
import os

log = logging.getLogger("presek")

def load_env():
    """Manually load .env file if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        # Remove quotes if present
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            log.warning(f"Could not load .env file: {e}")

load_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")

DB_RETAIN_DAYS = int(os.environ.get("DB_RETAIN_DAYS", 14))

# Initialize a global connection pool
try:
    _db_pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=30,
        dsn=DATABASE_URL
    )
except Exception as e:
    log.error(f"Failed to initialize database connection pool: {e}")
    _db_pool = None

class PooledConnectionWrapper:
    """Wraps a connection from the pool so .close() returns it instead of closing it."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        
    def __getattr__(self, name):
        return getattr(self._conn, name)
        
    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=DictCursor)
        cur.execute(sql, params)
        return cur
        
    def cursor(self, *args, **kwargs):
        if 'cursor_factory' not in kwargs:
            kwargs['cursor_factory'] = DictCursor
        return self._conn.cursor(*args, **kwargs)
        
    def close(self):
        if self._pool and self._conn:
            self._pool.putconn(self._conn)
            self._conn = None

def get_db():
    """Get a database connection from the pool with DictCursor enabled."""
    if _db_pool:
        try:
            conn = _db_pool.getconn()
            return PooledConnectionWrapper(conn, _db_pool)
        except Exception as e:
            log.error(f"Failed to get connection from pool: {e}")
            # Fallback if pool fails
            return psycopg2.connect(DATABASE_URL)
    else:
        # Fallback if pool initialization failed
        return psycopg2.connect(DATABASE_URL)

def get_db_size():
    """Get the size of the PostgreSQL database in MB."""
    try:
        conn = get_db()
        cur = conn.cursor()
        # Extract database name from URL (simple version)
        db_name = DATABASE_URL.split('/')[-1].split('?')[0]
        cur.execute("SELECT pg_database_size(%s)", (db_name,))
        size_bytes = cur.fetchone()[0]
        cur.close()
        conn.close()
        return round(size_bytes / (1024 * 1024), 2)
    except Exception as e:
        log.error(f"Failed to get database size: {e}")
        return 0.0

def init_db():
    """Initialize the database schema."""
    conn = get_db()
    cur = conn.cursor()
    
    # Create tables with reorganized schema if new install
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
        is_translated INTEGER DEFAULT 0
    )""")
    
    # Migrations for articles
    try:
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS subcategory TEXT DEFAULT ''")
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS topic TEXT DEFAULT 'Вести'")
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS original_title TEXT DEFAULT ''")
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS original_description TEXT DEFAULT ''")
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_translated INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS search_vector tsvector")
        conn.commit()
    except:
        conn.rollback()

    # Trigger for automatic search vector updates
    cur.execute("""
        CREATE OR REPLACE FUNCTION articles_search_trigger() RETURNS trigger AS $$
        begin
          new.search_vector :=
            setweight(to_tsvector('simple', coalesce(new.title,'')), 'A') ||
            setweight(to_tsvector('simple', coalesce(new.description,'')), 'B');
          return new;
        end
        $$ LANGUAGE plpgsql;
    """)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'tsvectorupdate') THEN
                CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
                ON articles FOR EACH ROW EXECUTE FUNCTION articles_search_trigger();
            END IF;
        END $$;
    """)

    cur.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
        cluster_id TEXT PRIMARY KEY,
        summary TEXT,
        perspectives JSONB DEFAULT '[]',
        created_at TIMESTAMP
    )""")
    
    # Migrations for cluster_summaries
    try:
        cur.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS perspectives JSONB DEFAULT '[]'")
        conn.commit()
    except:
        conn.rollback()

    cur.execute("""CREATE TABLE IF NOT EXISTS cluster_metadata (
        cluster_id TEXT PRIMARY KEY,
        tags TEXT[],
        topics TEXT[],
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS cluster_entities (
        cluster_id TEXT,
        entity_name TEXT,
        entity_type TEXT, -- 'PERSON' or 'ORG'
        PRIMARY KEY (cluster_id, entity_name)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS daily_briefings (
        date DATE PRIMARY KEY,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS reactions (
        cluster_id TEXT,
        emoji TEXT,
        count INTEGER DEFAULT 1,
        PRIMARY KEY (cluster_id, emoji)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS subscribers (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Ensure indexes exist for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_country_created ON articles(country, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_category_created ON articles(category, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_topic_created ON articles(topic, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_source_created ON articles(source, created_at DESC)")

    # Full Text Search Index
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING GIN (to_tsvector('simple', title || ' ' || COALESCE(description, '')))")
    
    conn.commit()
    cur.close()
    conn.close()

def prune_db():
    """Delete articles older than DB_RETAIN_DAYS and clean up orphaned metadata."""
    conn = None
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=DB_RETAIN_DAYS)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM articles WHERE created_at < %s", (cutoff,))
        deleted = cur.rowcount

        # Clean up orphaned metadata for clusters that no longer have articles
        cur.execute("""DELETE FROM cluster_summaries
                       WHERE cluster_id NOT IN (SELECT DISTINCT cluster_id FROM articles)""")
        orphan_summaries = cur.rowcount
        cur.execute("""DELETE FROM cluster_metadata
                       WHERE cluster_id NOT IN (SELECT DISTINCT cluster_id FROM articles)""")
        orphan_meta = cur.rowcount
        cur.execute("""DELETE FROM cluster_entities
                       WHERE cluster_id NOT IN (SELECT DISTINCT cluster_id FROM articles)""")
        orphan_entities = cur.rowcount
        cur.execute("""DELETE FROM reactions
                       WHERE cluster_id NOT IN (SELECT DISTINCT cluster_id FROM articles)""")
        orphan_reactions = cur.rowcount

        conn.commit()
        cur.close()
        if deleted:
            log.info(f"Pruned {deleted} articles older than {DB_RETAIN_DAYS} days.")
        orphan_total = orphan_summaries + orphan_meta + orphan_entities + orphan_reactions
        if orphan_total:
            log.info(f"Cleaned up {orphan_total} orphaned metadata rows "
                     f"(summaries={orphan_summaries}, meta={orphan_meta}, "
                     f"entities={orphan_entities}, reactions={orphan_reactions}).")
    except Exception as e:
        log.error(f"Prune error: {e}")
    finally:
        if conn:
            conn.close()
