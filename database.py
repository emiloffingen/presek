import sqlite3
import datetime
import logging
import os
from config import DB_PATH, DB_RETAIN_DAYS

log = logging.getLogger("presek")

def get_db() -> sqlite3.Connection:
    """Get a database connection with Row factory enabled."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database schema."""
    conn = get_db()
    
    # Create tables with reorganized schema if new install
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        created_at TEXT NOT NULL,
        image_url TEXT,
        clicks INTEGER DEFAULT 0,
        original_description TEXT DEFAULT '',
        is_translated INTEGER DEFAULT 0
    )""")
    
    conn.execute("""CREATE TABLE IF NOT EXISTS cluster_summaries (
        cluster_id TEXT PRIMARY KEY,
        summary TEXT,
        created_at TEXT
    )""")
    
    # Ensure indexes exist for performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cluster_id ON articles(cluster_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_country_created ON articles(country, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category_created ON articles(category, created_at DESC)")
    
    # Handle Migrations for existing DB
    cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if "image_url" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT DEFAULT ''")
    if "clicks" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN clicks INTEGER DEFAULT 0")
    if "description" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN description TEXT DEFAULT ''")
    if "subcategory" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN subcategory TEXT DEFAULT ''")
    if "country" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN country TEXT DEFAULT '🇲🇰'")
    if "original_title" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN original_title TEXT DEFAULT ''")
    if "original_description" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN original_description TEXT DEFAULT ''")
    if "is_translated" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN is_translated INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()

def prune_db():
    """Delete articles older than DB_RETAIN_DAYS and reclaim disk space."""
    try:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=DB_RETAIN_DAYS)).isoformat()
        conn = get_db()
        result = conn.execute("DELETE FROM articles WHERE created_at < ?", (cutoff,))
        deleted = result.rowcount
        conn.execute("VACUUM")
        conn.commit()
        conn.close()
        if deleted:
            log.info(f"Pruned {deleted} articles older than {DB_RETAIN_DAYS} days.")
    except Exception as e:
        log.error(f"Prune error: {e}")
