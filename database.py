import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
import datetime
import logging
import os

log = logging.getLogger("presek")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")
DB_RETAIN_DAYS = int(os.environ.get("DB_RETAIN_DAYS", 14))

# Initialize a global connection pool
try:
    _db_pool = SimpleConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=DATABASE_URL
    )
except Exception as e:
    log.error(f"Failed to initialize database connection pool: {e}")
    _db_pool = None

class PostgresConnection(psycopg2.extensions.connection):
    def execute(self, sql, params=None):
        cur = self.cursor(cursor_factory=DictCursor)
        cur.execute(sql, params)
        return cur

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
        
    def close(self):
        if self._pool and self._conn:
            self._pool.putconn(self._conn)
            self._conn = None

def get_db():
    """Get a database connection from the pool with DictCursor enabled."""
    if _db_pool:
        conn = _db_pool.getconn()
        return PooledConnectionWrapper(conn, _db_pool)
    else:
        # Fallback if pool initialization failed
        conn = psycopg2.connect(DATABASE_URL, connection_factory=PostgresConnection)
        return conn

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
    
    cur.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
        cluster_id TEXT PRIMARY KEY,
        summary TEXT,
        perspectives JSONB DEFAULT '[]',
        created_at TIMESTAMP
    )""")

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
    
    # Full Text Search Index
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING GIN (to_tsvector('simple', title || ' ' || COALESCE(description, '')))")
    
    conn.commit()
    cur.close()
    conn.close()

def prune_db():
    """Delete articles older than DB_RETAIN_DAYS."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=DB_RETAIN_DAYS)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM articles WHERE created_at < %s", (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            log.info(f"Pruned {deleted} articles older than {DB_RETAIN_DAYS} days.")
    except Exception as e:
        log.error(f"Prune error: {e}")
