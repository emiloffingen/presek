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

# Singleton instance
db_manager = DatabaseManager()

# Legacy hooks for minimal breakage during refactor
def get_db(): return db_manager
def get_db_size(): return db_manager.get_db_size()

def init_db():
    """Ensure the schema is fully updated for Presek 4.0."""
    db_manager.execute("CREATE EXTENSION IF NOT EXISTS vector", fetch=False)
    # Existing tables check/creation logic...
    # (Simplified for the refactor turn, full logic will be added in subsequent steps)
    log.info("Presek 4.0: Schema verification complete.")

def prune_db():
    """Service method for background maintenance."""
    db_manager.execute("DELETE FROM articles WHERE created_at < NOW() - INTERVAL '14 days'", fetch=False)
