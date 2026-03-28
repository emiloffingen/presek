import psycopg2
from psycopg2.extras import DictCursor, RealDictCursor
import datetime
import logging
import os

log = logging.getLogger("presek")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")
DB_RETAIN_DAYS = int(os.environ.get("DB_RETAIN_DAYS", 14))

class PostgresConnection(psycopg2.extensions.connection):
    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

def get_db():
    """Get a database connection with DictCursor enabled."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor, connection_factory=PostgresConnection)
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
        created_at TIMESTAMP
    )""")
    
    # Ensure indexes exist for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_country_created ON articles(country, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_category_created ON articles(category, created_at DESC)")
    
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
