import psycopg
import asyncio
from psycopg_pool import AsyncConnectionPool, ConnectionPool
from psycopg.rows import dict_row
from contextlib import contextmanager, asynccontextmanager
from collections import defaultdict
import alembic.config
import alembic.command
import logging
import time
import os
from version import APP_VERSION_LABEL

# --- Security: Input Validation for SQL ---

# Valid timespan values and their corresponding SQL fragments
VALID_TIMESPANS = {
    "24h": "AND created_at >= NOW() - INTERVAL '24 hours'",
    "7d": "AND created_at >= NOW() - INTERVAL '7 days'",
    "30d": "AND created_at >= NOW() - INTERVAL '30 days'",
    None: "",
    "": "",
}

# Valid sort options
VALID_SORT_BY = {"hybrid", "recent"}


def _validate_timespan(timespan: str | None) -> str:
    """Validate timespan parameter and return safe SQL WHERE clause fragment.
    
    Security: Only allows predefined timespan values to prevent SQL injection.
    Returns empty string for None or invalid values.
    """
    if timespan is None:
        return ""
    # Normalize to lowercase for case-insensitive matching
    normalized = timespan.lower() if isinstance(timespan, str) else ""
    return VALID_TIMESPANS.get(normalized, "")


def _validate_sort_by(sort_by: str) -> str:
    """Validate sort_by parameter to prevent SQL injection.
    
    Returns 'hybrid' for invalid values.
    """
    if isinstance(sort_by, str) and sort_by.lower() in VALID_SORT_BY:
        return sort_by.lower()
    return "hybrid"


# --- SQL Query Catalog ---

DB_SESSION_OPTIONS = (
    "-c statement_timeout=120000 "
    "-c idle_in_transaction_session_timeout=60000 "
    "-c timezone=Europe/Skopje"
)

SQL_SEMANTIC_SEARCH = """
    SELECT *, (1 - (embedding <=> %s::vector)) as similarity
    FROM articles
    WHERE embedding IS NOT NULL
      AND created_at >= NOW() - INTERVAL '7 days'
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""

SQL_ARTICLE_SEARCH = """
    WITH query AS (
        SELECT
            websearch_to_tsquery('simple', %s) AS ts_query,
            lower(%s) AS query_text,
            %s::vector AS query_vector
    )
    SELECT
        a.*,
        ts_rank_cd(a.search_vector, query.ts_query) AS rank,
        (1 - (a.embedding <=> query.query_vector)) AS semantic_score,
        CASE
            WHEN lower(a.title) = query.query_text THEN 4
            WHEN lower(a.title) LIKE query.query_text || '%%' THEN 3
            WHEN lower(a.title) LIKE '%%' || query.query_text || '%%' THEN 2
            WHEN lower(coalesce(a.description, '')) LIKE '%%' || query.query_text || '%%' THEN 1
            ELSE 0
        END AS match_score
    FROM articles a
    CROSS JOIN query
    WHERE {time_filter} (a.search_vector @@ query.ts_query OR (a.embedding <=> query.query_vector) < 0.6)
    ORDER BY (match_score * 2 + ts_rank_cd(a.search_vector, query.ts_query) + (1 - (a.embedding <=> query.query_vector)) * 5) DESC
    LIMIT %s
"""


def _build_hybrid_search_sql(time_filter: str, sort_by: str) -> str:
    """Helper to build dynamic hybrid search SQL.
    
    Security: time_filter and sort_by must be validated by caller to prevent SQL injection.
    time_filter should only contain safe WHERE clause fragments (e.g., "AND created_at >= ...")
    sort_by should only be "hybrid" or "recent"
    """
    # Validate sort_by to prevent SQL injection
    if sort_by not in ("hybrid", "recent"):
        sort_by = "hybrid"
    
    order_clause = "hybrid_score DESC" if sort_by == "hybrid" else "created_at DESC"
    
    return f"""
        WITH fts_results AS (
            SELECT id, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('simple', %s)
            {time_filter}
            ORDER BY rank DESC
            LIMIT 300
        ),
        semantic_results AS (
            SELECT id, (1 - (embedding <=> %s::vector)) AS similarity
            FROM articles
            WHERE embedding IS NOT NULL
              AND created_at >= NOW() - INTERVAL '30 days'
              {time_filter}
            ORDER BY similarity DESC
            LIMIT 300
        ),
        scored_articles AS (
            SELECT a.*, 
                   (COALESCE(f.rank, 0) * 0.45 + COALESCE(s.similarity, 0) * 0.55) AS base_score,
                   -- Sharper recency decay: 1.0 for now, 0.2 after 7 days
                   GREATEST(0.1, 1.0 - (EXTRACT(EPOCH FROM (NOW() - a.created_at)) / 604800)) as recency_factor
            FROM articles a
            LEFT JOIN fts_results f ON a.id = f.id
            LEFT JOIN semantic_results s ON a.id = s.id
            WHERE f.id IS NOT NULL OR (s.id IS NOT NULL AND s.similarity > 0.35)
        ),
        ranked_clusters AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY cluster_id ORDER BY base_score DESC) as cluster_rank
            FROM scored_articles
        )
        SELECT *, (base_score * recency_factor) as hybrid_score
        FROM ranked_clusters
        WHERE cluster_rank = 1
        ORDER BY {order_clause}
        LIMIT %s
    """


try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

log = logging.getLogger("presek")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        log.warning("Invalid %s=%r; falling back to %s", name, raw, default)
        return default


DB_POOL_MINCONN = max(1, _int_env("DB_POOL_MINCONN", 1))
DB_POOL_MAXCONN = max(DB_POOL_MINCONN, _int_env("DB_POOL_MAXCONN", 5))


class AsyncDatabaseManager:
    """Modern Async Database Layer using psycopg 3."""

    _instance = None
    _pool = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AsyncDatabaseManager, cls).__new__(cls)
        return cls._instance

    def _reset_pool(self):
        """Force re-initialization of the async pool. Crucial after process forking."""
        if self._pool:
            try:
                # We can't easily close an async pool from a sync signal handler
                # but we can at least null it out so the next async call re-inits
                self._pool = None
            except Exception as e:
                log.debug(f"Failed to close async pool: {e}")

    async def _ensure_pool(self):
        async with self._lock:
            if self._pool is None:
                self._pool = AsyncConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MINCONN,
                    max_size=DB_POOL_MAXCONN,
                    open=False,
                    kwargs={
                        "row_factory": dict_row,
                        "connect_timeout": 5,
                        "options": DB_SESSION_OPTIONS,
                    },
                )
                await self._pool.open()
                log.info(
                    f"Presek {APP_VERSION_LABEL}: Async database pool initialized (min={DB_POOL_MINCONN}, max={DB_POOL_MAXCONN})."
                )

    async def execute(self, sql, params=None, fetch=True):
        await self._ensure_pool()
        try:
            async with self._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    if fetch:
                        return await cur.fetchall()
                    await conn.commit()
                    return cur.rowcount
        except Exception as e:
            log.error(f"Presek {APP_VERSION_LABEL} Async DB Error: {e}")
            raise

    async def execute_one(self, sql, params=None):
        results = await self.execute(sql, params)
        return results[0] if results else None

    @asynccontextmanager
    async def connection(self):
        await self._ensure_pool()
        async with self._pool.connection() as conn:
            yield conn


class DatabaseManager:
    """Centralized Database Access Layer (DAL) for Presek 5.x."""

    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._init_pool()
        return cls._instance

    def _init_pool(self, retries=3, backoff_base=2):
        """Initialize connection pool with exponential backoff retry logic."""
        for attempt in range(retries):
            try:
                self._pool = ConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MINCONN,
                    max_size=DB_POOL_MAXCONN,
                    open=True,
                    kwargs={
                        "row_factory": dict_row,
                        "connect_timeout": 5,
                        "options": DB_SESSION_OPTIONS,
                    },
                )
                log.info(
                    f"Presek {APP_VERSION_LABEL}: Database connection pool initialized "
                    f"(min={DB_POOL_MINCONN}, max={DB_POOL_MAXCONN}, connect_timeout=5s)."
                )
                return
            except Exception as e:
                if attempt < retries - 1:
                    wait_time = backoff_base**attempt
                    log.warning(
                        f"Database connection failed (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    log.error(
                        f"Failed to initialize database connection pool after {retries} attempts: {e}"
                    )
                    self._pool = None

    def _reset_pool(self):
        """Force re-initialization of the pool. Crucial after process forking."""
        if self._pool:
            try:
                self._pool.close()
            except Exception as e:
                log.warning(f"Failed to close connection pool: {e}")
        self._pool = None
        self._init_pool()

    def get_conn(self):
        if not self._pool:
            return psycopg.connect(DATABASE_URL, row_factory=dict_row)
        return self._pool.getconn()

    def put_conn(self, conn):
        if self._pool:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                log.warning(f"Failed to return connection to pool: {e}")
        else:
            conn.close()

    def execute(self, sql, params=None, fetch=True):
        """Standardized query execution with automatic connection release."""
        conn = None
        try:
            conn = self.get_conn()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                results = None
                if fetch:
                    results = cur.fetchall()
                conn.commit()
                return results if fetch else cur.rowcount
        except Exception as e:
            if conn:
                conn.rollback()
            log.error(f"Presek {APP_VERSION_LABEL} DB Error: {e}")
            raise
        finally:
            if conn:
                self.put_conn(conn)

    def execute_one(self, sql, params=None):
        results = self.execute(sql, params)
        return results[0] if results else None

    async def async_execute(self, sql, params=None, fetch=True):
        """Asynchronous execution via native psycopg 3 async pool."""
        return await async_db.execute(sql, params, fetch)

    async def async_execute_one(self, sql, params=None):
        """Asynchronous execution of single row query via native async pool."""
        return await async_db.execute_one(sql, params)

    @contextmanager
    def connection(self):
        """Context manager for obtaining and returning a connection."""
        conn = self.get_conn()
        try:
            yield conn
        finally:
            self.put_conn(conn)

    # --- High-Level DAL Methods ---

    async def async_get_articles_by_ids(self, ids):
        return await self.async_execute(
            "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
            (ids,),
        )

    async def async_search_semantic(
        self, query_embedding: list[float], limit: int = 100
    ):
        vec_str = "[" + ",".join(map(str, query_embedding)) + "]"
        return await self.async_execute(SQL_SEMANTIC_SEARCH, (vec_str, vec_str, limit))

    async def async_hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        limit: int = 50,
        sort_by: str = "hybrid",
        timespan: str | None = None,
    ):
        # Validate inputs to prevent SQL injection
        time_filter = _validate_timespan(timespan)
        validated_sort_by = _validate_sort_by(sort_by)

        vec_str = "[" + ",".join(map(str, query_embedding)) + "]"
        sql = _build_hybrid_search_sql(time_filter, validated_sort_by)
        return await self.async_execute(sql, (query_text, query_text, vec_str, limit))

    async def async_search_articles(
        self, query: str, limit: int = 50, timespan: str | None = None
    ):
        # Validate timespan to prevent SQL injection
        time_filter = _validate_timespan(timespan)
        # Remove leading "AND " for this query format
        if time_filter.startswith("AND "):
            time_filter = time_filter[4:]

        sql = SQL_ARTICLE_SEARCH.format(time_filter=time_filter)
        return await self.async_execute(sql, (query, query, None, limit))

    async def async_get_synthesis_ids(self, cluster_ids: list[str]):
        if not cluster_ids:
            return []
        rows = await self.async_execute(
            "SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)",
            (cluster_ids,),
        )
        return [r["cluster_id"] for r in rows]

    def get_articles_by_ids(self, ids):
        return self.execute(
            "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
            (ids,),
        )

    def search_semantic(self, query_embedding: list[float], limit: int = 100):
        """
        Search for articles using vector similarity (cosine distance).
        Returns articles from clusters that are semantically close to the query.
        """
        # Ensure embedding is passed as a string representation of the list for pgvector
        vec_str = "[" + ",".join(map(str, query_embedding)) + "]"
        return self.execute(SQL_SEMANTIC_SEARCH, (vec_str, vec_str, limit))

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        limit: int = 50,
        sort_by: str = "hybrid",
        timespan: str | None = None,
    ):
        """
        Combines Full-Text Search (FTS) and Semantic Search (pgvector) using a weighted score.
        Supports advanced web-style queries (e.g. "phrase search", -exclude).
        """
        vec_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # Validate inputs to prevent SQL injection
        time_filter = _validate_timespan(timespan)
        validated_sort_by = _validate_sort_by(sort_by)

        # We use websearch_to_tsquery for more natural search behavior
        sql = _build_hybrid_search_sql(time_filter, validated_sort_by)
        return self.execute(sql, (query_text, query_text, vec_str, limit))

    def get_articles_by_country(
        self, country, limit=200, sub=None, topic=None, sentiment=None, category=None
    ):
        sql = "SELECT * FROM articles WHERE 1=1"
        params = []

        if category:
            sql += " AND category = %s"
            params.append(category)
        elif country and country != "MK":
            sql += " AND country = %s"
            params.append(country)
        elif country == "MK":
            sql += " AND (country = 'MK' OR country IS NULL OR country = '')"

        if sub:
            sql += " AND subcategory = %s"
            params.append(sub)
        if topic:
            sql += " AND topic = %s"
            params.append(topic)
        if sentiment:
            escaped_sentiment = (
                sentiment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            sql += " AND summary ILIKE %s ESCAPE '\\'"
            params.append(f"%{escaped_sentiment}%")

        # Ensure limit is an integer
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 200

        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self.execute(sql, tuple(params))

    def get_personalized_articles(self, follow_sources, follow_topics, limit=200):
        sql = "SELECT * FROM articles WHERE 1=1"
        clauses = []
        params = []
        if follow_sources:
            clauses.append("source = ANY(%s)")
            params.append(follow_sources)
        if follow_topics:
            clauses.append("topic = ANY(%s)")
            params.append(follow_topics)
        if clauses:
            sql += " AND (" + " OR ".join(clauses) + ")"

        # Ensure limit is an integer
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 200

        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self.execute(sql, tuple(params))

    def search_articles(self, q, limit=100):
        if not q or len(q) > 500:
            return []

        # Generate embedding for semantic search
        from embeddings import generate_query_embedding

        vector = generate_query_embedding(q)
        vector_str = "[" + ",".join(map(str, vector)) + "]" if vector else None

        # Ensure limit is an integer
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 100

        return self.execute(SQL_ARTICLE_SEARCH, (q, q, vector_str, limit))

    def get_synthesis_ids(self, cluster_ids):
        if not cluster_ids:
            return []
        rows = self.execute(
            "SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)",
            (cluster_ids,),
        )
        return [r["cluster_id"] for r in rows]

    def get_cluster_entities(self, cluster_ids):
        if not cluster_ids:
            return {}
        rows = self.execute(
            "SELECT cluster_id, entity_name FROM cluster_entities WHERE cluster_id = ANY(%s)",
            (cluster_ids,),
        )
        result = defaultdict(set)
        for r in rows:
            result[r["cluster_id"]].add(r["entity_name"])
        return result

    def get_db_size(self):
        db_name = DATABASE_URL.split("/")[-1].split("?")[0]
        row = self.execute_one("SELECT pg_database_size(%s)", (db_name,))
        if row:
            size_bytes = list(row.values())[0]
            return round(size_bytes / (1024 * 1024), 2)
        return 0.0

    def get_stats(self):
        try:
            total_row = self.execute_one("SELECT COUNT(*) FROM articles")
            total = total_row["count"] if total_row else 0

            by_cat = (
                self.execute(
                    "SELECT category, COUNT(*) n FROM articles GROUP BY category ORDER BY n DESC"
                )
                or []
            )
            by_source = (
                self.execute(
                    "SELECT source, COUNT(*) n FROM articles GROUP BY source ORDER BY n DESC"
                )
                or []
            )

            recent_24h_row = self.execute_one(
                "SELECT COUNT(*) FROM articles WHERE COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '1 day'"
            )
            recent_24h = recent_24h_row["count"] if recent_24h_row else 0

            recent_1h_row = self.execute_one(
                "SELECT COUNT(*) FROM articles WHERE COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '1 hour'"
            )
            recent_1h = recent_1h_row["count"] if recent_1h_row else 0

            summarized_row = self.execute_one(
                "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''"
            )
            summarized = summarized_row["count"] if summarized_row else 0

            return {
                "total_articles": total,
                "by_category": by_cat,
                "by_source": by_source,
                "last_24h": recent_24h,
                "last_1h": recent_1h,
                "summarized": summarized,
            }
        except Exception as e:
            log.error(f"Error getting stats: {e}")
            return {
                "total_articles": 0,
                "by_category": [],
                "by_source": [],
                "last_24h": 0,
                "last_1h": 0,
                "summarized": 0,
            }

    def init_schema(self):
        """Unified Schema management via Alembic."""
        try:
            # Check for Alembic config file
            ini_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "alembic.ini"
            )
            if not os.path.exists(ini_path):
                log.warning(
                    f"Alembic config not found at {ini_path}, skipping migrations."
                )
                return

            cfg = alembic.config.Config(ini_path)
            # Ensure URL is set correctly from env
            cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

            log.info(f"Presek {APP_VERSION_LABEL}: Running database migrations...")
            alembic.command.upgrade(cfg, "head")
            log.info(f"Presek {APP_VERSION_LABEL}: Schema verification complete.")
        except Exception as e:
            log.error(f"Migration error: {e}")
            # Fallback to legacy behavior if migrations fail during transition?
            # For now, we want to know if it fails.
            raise


# --- Legacy Compatibility Wrapper ---


class DBWrapper:
    """Wraps a connection to support .cursor(), .execute(), .fetchone(), .fetchall(), and .close() for legacy code."""

    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.get_conn()

    def cursor(self):
        return self.conn.cursor()

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


db_manager = DatabaseManager()
async_db = AsyncDatabaseManager()


def get_db():
    return DBWrapper(db_manager)


def get_db_size():
    return db_manager.get_db_size()


def init_db():
    db_manager.init_schema()


def prune_db():
    from config import DB_RETAIN_DAYS, DB_RETAIN_FAILED_TASKS_DAYS

    interval = f"{int(DB_RETAIN_DAYS)} days"
    failed_interval = f"{int(DB_RETAIN_FAILED_TASKS_DAYS)} days"
    # Delete old articles
    db_manager.execute(
        "DELETE FROM articles WHERE created_at < NOW() - INTERVAL %s",
        (interval,),
        fetch=False,
    )

    # Clean up orphaned metadata/summaries efficiently using NOT EXISTS
    db_manager.execute(
        """
        DELETE FROM cluster_summaries cs WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = cs.cluster_id);
        DELETE FROM cluster_metadata cm WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = cm.cluster_id);
        DELETE FROM cluster_entities ce WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = ce.cluster_id);
        DELETE FROM reactions r WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = r.cluster_id);
        DELETE FROM failed_tasks WHERE created_at < NOW() - INTERVAL %s;
    """,
        (failed_interval,),
        fetch=False,
    )
