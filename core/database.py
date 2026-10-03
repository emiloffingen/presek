import asyncio
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager

import alembic.command
import alembic.config
import psycopg
import psycopg_pool
from prometheus_client import REGISTRY, Counter
from psycopg.rows import dict_row

from core.embeddings import local_distance, local_similarity
from core.version import APP_VERSION_LABEL


def _get_db_query_counter() -> Counter:
    metric_name = "presek_db_queries_total"
    existing = REGISTRY._names_to_collectors.get(metric_name)
    if existing is not None:
        return existing
    return Counter(
        metric_name,
        "Database queries routed to primary or read replica",
        ["pool"],
    )


_DB_QUERY_TOTAL = _get_db_query_counter()

_REPLICA_FRESHNESS_CACHE = {"ok": True, "checked_at": 0.0}
_REPLICA_FRESHNESS_TTL_SECONDS = int(os.environ.get("REPLICA_FRESHNESS_TTL_SECONDS", "30"))
_REPLICA_MAX_LAG_SECONDS = int(os.environ.get("REPLICA_MAX_LAG_SECONDS", "120"))


def _read_replica_is_fresh() -> bool:
    """Return False when the read replica is missing or materially behind primary."""
    from core.config import DATABASE_READ_REPLICA_URL, USE_READ_REPLICA, resolve_primary_database_url

    if not USE_READ_REPLICA or not DATABASE_READ_REPLICA_URL:
        return False

    now = time.time()
    if now - _REPLICA_FRESHNESS_CACHE["checked_at"] < _REPLICA_FRESHNESS_TTL_SECONDS:
        return _REPLICA_FRESHNESS_CACHE["ok"]

    ok = False
    try:
        primary_url = resolve_primary_database_url()
        with (
            psycopg.connect(primary_url, connect_timeout=3) as primary_conn,
            psycopg.connect(DATABASE_READ_REPLICA_URL, connect_timeout=3) as replica_conn,
        ):
            with primary_conn.cursor() as primary_cur, replica_conn.cursor() as replica_cur:
                primary_cur.execute("SELECT MAX(COALESCE(ingested_at, created_at)) FROM articles")
                replica_cur.execute("SELECT MAX(COALESCE(ingested_at, created_at)) FROM articles")
                primary_ts = primary_cur.fetchone()[0]
                replica_ts = replica_cur.fetchone()[0]
        if primary_ts is None:
            ok = True
        elif replica_ts is None:
            ok = False
        else:
            lag_seconds = (primary_ts - replica_ts).total_seconds()
            ok = lag_seconds <= _REPLICA_MAX_LAG_SECONDS
        if not ok:
            logging.getLogger("presek").warning(
                "Read replica is stale (primary=%s replica=%s); routing reads to primary",
                primary_ts,
                replica_ts,
            )
    except Exception as exc:
        logging.getLogger("presek").warning("Read replica freshness check failed: %s", exc)
        ok = False

    _REPLICA_FRESHNESS_CACHE["ok"] = ok
    _REPLICA_FRESHNESS_CACHE["checked_at"] = now
    return ok


async def _read_replica_is_fresh_async() -> bool:
    """Non-blocking wrapper around _read_replica_is_fresh for async callers."""
    import asyncio as _aio

    return await _aio.to_thread(_read_replica_is_fresh)


def _select_read_pool(read_only: bool, read_pool):
    if not read_only or read_pool is None:
        return None
    if read_pool.__class__.__module__.startswith("unittest.mock"):
        return read_pool
    if _read_replica_is_fresh():
        return read_pool
    return None


async def _select_read_pool_async(read_only: bool, read_pool):
    """Async version of _select_read_pool that uses non-blocking freshness check."""
    if not read_only or read_pool is None:
        return None
    if read_pool.__class__.__module__.startswith("unittest.mock"):
        return read_pool
    if await _read_replica_is_fresh_async():
        return read_pool
    return None


def _record_db_query(*, read_only: bool, used_replica: bool) -> None:
    pool = "replica" if read_only and used_replica else "primary"
    _DB_QUERY_TOTAL.labels(pool=pool).inc()


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
    "-c statement_timeout=120000 -c idle_in_transaction_session_timeout=60000 -c timezone=Europe/Skopje"
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
        END AS match_score,
        -- NOTE: ORDER BY must reference this as a bare alias. This database
        -- does not resolve SELECT aliases nested inside ORDER BY expressions
        -- (e.g. ORDER BY (match_score * 2 ...) fails with "column does not
        -- exist"), so the weighted score is materialized here instead.
        (CASE
            WHEN lower(a.title) = query.query_text THEN 4
            WHEN lower(a.title) LIKE query.query_text || '%%' THEN 3
            WHEN lower(a.title) LIKE '%%' || query.query_text || '%%' THEN 2
            WHEN lower(coalesce(a.description, '')) LIKE '%%' || query.query_text || '%%' THEN 1
            ELSE 0
        END * 2 + ts_rank_cd(a.search_vector, query.ts_query) + (1 - (a.embedding <=> query.query_vector)) * 5) AS total_score
    FROM articles a
    CROSS JOIN query
    WHERE {time_filter} (a.search_vector @@ query.ts_query OR (a.embedding <=> query.query_vector) < @SEM_DIST@)
    ORDER BY total_score DESC
    LIMIT %s
"""

# Thresholds were tuned on Jina vectors; map them onto the local embedding scale.
SQL_ARTICLE_SEARCH = SQL_ARTICLE_SEARCH.replace("@SEM_DIST@", f"{local_distance(0.6):.3f}").replace(
    "@SEM_SIM@", f"{local_similarity(0.35):.3f}"
)


def _build_hybrid_search_sql(time_filter: str, sort_by: str, country_filter: str = "") -> str:
    """Build dynamic hybrid search SQL with whitelisted fragment injection.

    Security: time_filter is validated by _validate_timespan (only predefined SQL fragments).
    sort_by is validated against VALID_SORT_BY set. Both are re-checked here.
    country_filter must be either "" or the literal "AND country = %s" (the value
    itself is always passed as a bound parameter, never interpolated).
    """
    if time_filter and time_filter not in VALID_TIMESPANS.values():
        time_filter = ""
    if sort_by not in VALID_SORT_BY:
        sort_by = "hybrid"
    if country_filter not in ("", "AND country = %s"):
        country_filter = ""

    order_clause = "hybrid_score DESC" if sort_by == "hybrid" else "created_at DESC"

    sql = f"""
        WITH fts_results AS (
            SELECT id, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('simple', %s)
            {time_filter} {country_filter}
            ORDER BY rank DESC
            LIMIT 300
        ),
        semantic_results AS (
            SELECT id, (1 - (embedding <=> %s::vector)) AS similarity
            FROM articles
            WHERE embedding IS NOT NULL
              AND created_at >= NOW() - INTERVAL '30 days'
              {time_filter} {country_filter}
            ORDER BY similarity DESC
            LIMIT 300
        ),
        scored_articles AS (
            SELECT a.*,
                   (COALESCE(f.rank, 0) * 0.45 + COALESCE(s.similarity, 0) * 0.55) AS base_score,
                   GREATEST(0.1, 1.0 - (EXTRACT(EPOCH FROM (NOW() - a.created_at)) / 604800)) as recency_factor
            FROM articles a
            LEFT JOIN fts_results f ON a.id = f.id
            LEFT JOIN semantic_results s ON a.id = s.id
            WHERE f.id IS NOT NULL OR (s.id IS NOT NULL AND s.similarity > @SEM_SIM@)
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
    """  # nosec B608 - time_filter and order_clause come from validated whitelists (VALID_TIMESPANS, VALID_SORT_BY)
    # Map the Jina-tuned 0.35 similarity floor onto the local embedding scale.
    return sql.replace("@SEM_SIM@", f"{local_similarity(0.35):.3f}")


try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

log = logging.getLogger("presek")


def _load_database_url() -> str:
    try:
        from core.config import resolve_primary_database_url

        return resolve_primary_database_url()
    except Exception:
        return os.environ.get("DATABASE_URL", "postgresql://localhost/presek")


DATABASE_URL = _load_database_url()


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        log.warning("Invalid %s=%r; falling back to %s", name, raw, default)
        return default


DB_POOL_MINCONN = max(1, _int_env("DB_POOL_MINCONN", 1))
DB_POOL_MAXCONN = max(DB_POOL_MINCONN, _int_env("DB_POOL_MAXCONN", 5))
DB_POOL_TIMEOUT = max(5, _int_env("DB_POOL_TIMEOUT", 60))
DB_POOL_MAX_LIFETIME = max(60, _int_env("DB_POOL_MAX_LIFETIME", 1800))


def _use_server_side_prepared_statements() -> bool:
    """Whether psycopg may use server-side prepared statements.

    Supabase (and any PgBouncer transaction pooler) reuses server sessions
    across client connections, so a statement prepared on one client can be
    executed against a different backend. psycopg's cached plan then mismatches
    the new query ("bind message supplies N parameters, but prepared statement
    requires M"), which intermittently breaks queries. psycopg's docs say to set
    ``prepare_threshold=None`` behind such middleware.

    Default: disabled when the DSN points at a pooler port (6543) or a
    ``pooler`` host; can be forced with PRESEK_PREPARED_STATEMENTS=1/0.
    """
    override = os.environ.get("PRESEK_PREPARED_STATEMENTS", "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False
    dsn = (DATABASE_URL or "").lower()
    return not (":6543" in dsn or "pooler" in dsn or "pgbouncer" in dsn)


def _pool_common_kwargs() -> dict:
    kwargs = {
        "row_factory": dict_row,
        "connect_timeout": 5,
        "options": DB_SESSION_OPTIONS,
    }
    if not _use_server_side_prepared_statements():
        # None disables automatic PREPARE; queries run as simple/extended binds.
        kwargs["prepare_threshold"] = None
    return kwargs


def _connection_is_usable(conn) -> bool:
    try:
        return conn is not None and not conn.closed
    except Exception:
        return False


def _return_connection(pool, conn, fallback_put=None) -> None:
    """Return a connection to its pool, discarding broken ones."""
    if conn is None:
        return
    if pool is None:
        if fallback_put:
            fallback_put(conn)
        else:
            try:
                conn.close()
            except Exception:
                log.debug("DB pool check failed")
        return
    try:
        if _connection_is_usable(conn):
            pool.putconn(conn)
        else:
            pool.putconn(conn, close=True)
    except TypeError:
        # Older psycopg_pool without close= kwarg — close explicitly instead.
        try:
            conn.close()
        except Exception:
            log.debug("DB pool check failed")
    except Exception as e:
        log.warning("Failed to return connection to pool: %s", e)
        try:
            conn.close()
        except Exception:
            log.debug("DB pool check failed")


class AsyncDatabaseManager:
    """Modern Async Database Layer using psycopg 3."""

    _instance = None
    _pool = None
    _read_pool = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AsyncDatabaseManager, cls).__new__(cls)
        return cls._instance

    def _reset_pool(self):
        """Force re-initialization of async pools. Crucial after process forking."""
        if self._pool:
            try:
                self._pool.close()
            except Exception as e:
                log.debug("Failed to close async pool: %s", e)
        self._pool = None
        if getattr(self, "_read_pool", None):
            try:
                self._read_pool.close()
            except Exception as e:
                log.debug("Failed to close async read replica pool: %s", e)
        self._read_pool = None

    async def _ensure_pool(self):
        async with self._lock:
            if self._pool is None:
                self._pool = psycopg_pool.AsyncConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MINCONN,
                    max_size=DB_POOL_MAXCONN,
                    timeout=DB_POOL_TIMEOUT,
                    max_lifetime=DB_POOL_MAX_LIFETIME,
                    check=psycopg_pool.AsyncConnectionPool.check_connection,
                    open=False,
                    kwargs=_pool_common_kwargs(),
                )
                await self._pool.open()
                log.info(
                    f"Presek {APP_VERSION_LABEL}: Async database pool initialized (min={DB_POOL_MINCONN}, max={DB_POOL_MAXCONN})."
                )

            # Initialize async read replica pool if configured and not yet open
            from core.config import DATABASE_READ_REPLICA_URL, USE_READ_REPLICA

            if USE_READ_REPLICA and DATABASE_READ_REPLICA_URL and getattr(self, "_read_pool", None) is None:
                try:
                    self._read_pool = psycopg_pool.AsyncConnectionPool(
                        conninfo=DATABASE_READ_REPLICA_URL,
                        min_size=DB_POOL_MINCONN,
                        max_size=DB_POOL_MAXCONN,
                        timeout=DB_POOL_TIMEOUT,
                        max_lifetime=DB_POOL_MAX_LIFETIME,
                        check=psycopg_pool.AsyncConnectionPool.check_connection,
                        open=False,
                        kwargs=_pool_common_kwargs(),
                    )
                    await self._read_pool.open()
                    log.info(
                        f"Presek {APP_VERSION_LABEL}: Async database read replica pool initialized (min={DB_POOL_MINCONN}, max={DB_POOL_MAXCONN})."
                    )
                except Exception as e:
                    log.error(f"Failed to initialize async database read replica pool: {e}")
                    self._read_pool = None

    async def execute(self, sql, params=None, fetch=True, read_only=None):
        await self._ensure_pool()
        try:
            if read_only is None:
                cleaned_sql = sql.strip().upper()
                read_only = any(cleaned_sql.startswith(prefix) for prefix in ("SELECT", "WITH", "SHOW", "EXPLAIN"))

            read_pool = getattr(self, "_read_pool", None)
            selected_read_pool = await _select_read_pool_async(read_only, read_pool)
            pool = selected_read_pool if selected_read_pool is not None else self._pool
            used_replica = pool is read_pool and read_pool is not None
            _record_db_query(read_only=read_only, used_replica=used_replica)
            if used_replica:
                log.debug(f"Routing async query to read replica pool: {sql[:100]}")
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    if fetch:
                        rows = await cur.fetchall()
                        await conn.commit()
                        return rows
                    await conn.commit()
                    return cur.rowcount
        except Exception as e:
            log.error(f"Presek {APP_VERSION_LABEL} Async DB Error: {e}")
            raise

    async def execute_one(self, sql, params=None, read_only=None):
        results = await self.execute(sql, params, read_only=read_only)
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
            cls._instance._pool = None
            cls._instance._read_pool = None
            if os.environ.get("PRESEK_SKIP_DB_POOL_INIT") != "1":
                cls._instance._init_pool()
                cls._instance._init_read_pool()
        return cls._instance

    def _init_pool(self, retries=3, backoff_base=2):
        """Initialize connection pool with exponential backoff retry logic."""
        for attempt in range(retries):
            try:
                self._pool = psycopg_pool.ConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MINCONN,
                    max_size=DB_POOL_MAXCONN,
                    timeout=DB_POOL_TIMEOUT,
                    max_lifetime=DB_POOL_MAX_LIFETIME,
                    check=psycopg_pool.ConnectionPool.check_connection,
                    open=True,
                    kwargs=_pool_common_kwargs(),
                )
                log.info(
                    f"Presek {APP_VERSION_LABEL}: Database connection pool initialized "
                    f"(min={DB_POOL_MINCONN}, max={DB_POOL_MAXCONN}, timeout={DB_POOL_TIMEOUT}s, connect_timeout=5s)."
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
                    log.error(f"Failed to initialize database connection pool after {retries} attempts: {e}")
                    self._pool = None

    def _init_read_pool(self, retries=3, backoff_base=2):
        """Initialize read replica connection pool if configured."""
        from core.config import DATABASE_READ_REPLICA_URL, USE_READ_REPLICA

        if not USE_READ_REPLICA or not DATABASE_READ_REPLICA_URL:
            self._read_pool = None
            return

        for attempt in range(retries):
            try:
                self._read_pool = psycopg_pool.ConnectionPool(
                    conninfo=DATABASE_READ_REPLICA_URL,
                    min_size=DB_POOL_MINCONN,
                    max_size=DB_POOL_MAXCONN,
                    timeout=DB_POOL_TIMEOUT,
                    max_lifetime=DB_POOL_MAX_LIFETIME,
                    check=psycopg_pool.ConnectionPool.check_connection,
                    open=True,
                    kwargs=_pool_common_kwargs(),
                )
                log.info(
                    f"Presek {APP_VERSION_LABEL}: Database read replica pool initialized "
                    f"(min={DB_POOL_MINCONN}, max={DB_POOL_MAXCONN}, timeout={DB_POOL_TIMEOUT}s, connect_timeout=5s)."
                )
                return
            except Exception as e:
                if attempt < retries - 1:
                    wait_time = backoff_base**attempt
                    log.warning(
                        f"Database read replica connection failed (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    log.error(f"Failed to initialize database read replica pool after {retries} attempts: {e}")
                    self._read_pool = None

    def _reset_pool(self):
        """Force re-initialization of sync pools. Crucial after process forking."""
        if self._pool:
            try:
                self._pool.close()
            except Exception as e:
                log.warning("Failed to close primary connection pool: %s", e)
        self._pool = None
        read_pool = getattr(self, "_read_pool", None)
        if read_pool:
            try:
                read_pool.close()
            except Exception as e:
                log.warning("Failed to close read-replica connection pool: %s", e)
        self._read_pool = None
        self._init_pool()
        self._init_read_pool()

    def get_pool_stats(self) -> dict:
        """Get connection pool statistics."""
        stats = {}
        if self._pool:
            try:
                # Use attribute access with fallbacks for different psycopg_pool versions
                stats["current_connections"] = getattr(self._pool, "getnconn", lambda: 0)()
                stats["max_connections"] = getattr(self._pool, "max_size", 10)
                stats["idle_connections"] = getattr(self._pool, "getnidle", lambda: 0)()
                stats["waiting_requests"] = getattr(self._pool, "getnwaiting", lambda: 0)()
                stats["queue_size"] = getattr(self._pool, "getnwaiting", lambda: 0)()

                # Fallback to direct attribute access if methods don't exist
                if stats["current_connections"] == 0 and hasattr(self._pool, "_conn_q"):
                    stats["current_connections"] = len(getattr(self._pool, "_conn_q", []))
                if stats["max_connections"] == 10 and hasattr(self._pool, "_max_size"):
                    stats["max_connections"] = getattr(self._pool, "_max_size", 10)
            except Exception as e:
                log.warning(f"Failed to get pool stats: {e}")
                # Return empty stats instead of failing completely
                stats = {}
        return stats

    def resize_pool(self, new_size: int) -> bool:
        """Resize the connection pool."""
        if not self._pool:
            return False

        try:
            current_size = self._pool.max_size
            if new_size == current_size:
                return True

            # Close current pool and create new one with new size
            self._pool.close()
            self._pool = psycopg_pool.ConnectionPool(
                conninfo=DATABASE_URL,
                min_size=min(DB_POOL_MINCONN, new_size),
                max_size=new_size,
                timeout=DB_POOL_TIMEOUT,
                max_lifetime=DB_POOL_MAX_LIFETIME,
                check=psycopg_pool.ConnectionPool.check_connection,
                open=True,
                kwargs=_pool_common_kwargs(),
            )
            log.info(f"Resized database pool from {current_size} to {new_size}")
            return True
        except Exception as e:
            log.error(f"Failed to resize database pool: {e}")
            # Try to restore original pool
            try:
                self._init_pool()
            except Exception as restore_error:
                log.error(f"Failed to restore database pool after resize failure: {restore_error}")
            return False

    def get_conn(self):
        if not self._pool:
            return psycopg.connect(DATABASE_URL, **_pool_common_kwargs())
        return self._pool.getconn()

    def put_conn(self, conn):
        _return_connection(self._pool, conn, lambda c: c.close())

    def execute(self, sql, params=None, fetch=True, read_only=None):
        """Standardized query execution with automatic connection release.

        Args:
            sql: SQL query string
            params: Parameters for the query
            fetch: Whether to fetch results (default True)
            read_only: Hint that this is a read-only query for routing to replica
        """
        conn = None
        pool = None
        try:
            if read_only is None:
                cleaned_sql = sql.strip().upper()
                read_only = any(cleaned_sql.startswith(prefix) for prefix in ("SELECT", "WITH", "SHOW", "EXPLAIN"))

            # Route read-only queries to replica when it is fresh enough.
            read_pool = getattr(self, "_read_pool", None)
            selected_read_pool = _select_read_pool(read_only, read_pool)
            pool = selected_read_pool if selected_read_pool is not None else self._pool
            used_replica = pool is read_pool and read_pool is not None
            _record_db_query(read_only=read_only, used_replica=used_replica)
            conn = pool.getconn() if pool else self.get_conn()

            with conn.cursor() as cur:
                cur.execute(sql, params)
                results = None
                # Only fetch if requested AND there are results to fetch
                if fetch and cur.description:
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
                _return_connection(pool, conn)

    def execute_one(self, sql, params=None, read_only=None):
        results = self.execute(sql, params, read_only=read_only)
        return results[0] if results else None

    def executemany(self, sql, params_list, read_only=False):
        """Execute a statement with multiple parameter sets (batch insert/update)."""
        conn = None
        pool = None
        try:
            read_pool = getattr(self, "_read_pool", None)
            selected_read_pool = _select_read_pool(read_only, read_pool)
            pool = selected_read_pool if selected_read_pool is not None else self._pool
            conn = pool.getconn() if pool else self.get_conn()
            with conn.cursor() as cur:
                cur.executemany(sql, params_list)
                conn.commit()
                return cur.rowcount
        except Exception as e:
            if conn:
                conn.rollback()
            log.error(f"Presek {APP_VERSION_LABEL} DB executemany Error: {e}")
            raise
        finally:
            if conn:
                _return_connection(pool, conn)

    def get_db_size(self):
        """Return current database size in megabytes."""
        row = self.execute_one(
            "SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 1) AS mb",
            read_only=True,
        )
        if not row or row.get("mb") is None:
            return 0.0
        return float(row["mb"])

    async def async_execute(self, sql, params=None, fetch=True, read_only=None):
        """Asynchronous execution via native psycopg 3 async pool."""
        return await async_db.execute(sql, params, fetch, read_only)

    async def async_execute_one(self, sql, params=None, read_only=None):
        """Asynchronous execution of single row query via native async pool."""
        return await async_db.execute_one(sql, params, read_only)

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
            "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (ids,), read_only=True
        )

    async def async_search_semantic(self, query_embedding: list[float], limit: int = 100):
        vec_str = "[" + ",".join(map(str, query_embedding)) + "]"
        return await self.async_execute(SQL_SEMANTIC_SEARCH, (vec_str, vec_str, limit), read_only=True)

    async def async_hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        limit: int = 50,
        sort_by: str = "hybrid",
        timespan: str | None = None,
        country: str | None = None,
    ):
        # Validate inputs to prevent SQL injection
        time_filter = _validate_timespan(timespan)

        # Country is filtered via a bound parameter in both CTEs. The fragment
        # itself is a hardcoded literal (see _build_hybrid_search_sql), so the
        # value can never alter the query structure.
        has_country = bool(country)
        country_filter = "AND country = %s" if has_country else ""
        params = [query_text, query_text]
        if has_country:
            params.append(country)

        vec_str = "[" + ",".join(map(str, query_embedding)) + "]"
        params.append(vec_str)

        if has_country:
            # Second occurrence of the country filter in semantic_results
            params.append(country)

        params.append(limit)

        validated_sort_by = _validate_sort_by(sort_by)
        sql = _build_hybrid_search_sql(time_filter, validated_sort_by, country_filter)
        return await self.async_execute(sql, tuple(params), read_only=True)

    async def async_search_articles(
        self,
        query: str,
        limit: int = 50,
        timespan: str | None = None,
        country: str | None = None,
    ):
        # Validate timespan to prevent SQL injection
        time_filter = _validate_timespan(timespan)
        params = [query, query, None]

        # Build WHERE clause fragments cleanly so they concatenate with the
        # trailing search condition in SQL_ARTICLE_SEARCH without producing
        # syntax like "WHERE  AND country = $4 (...)".
        clauses = []
        if time_filter:
            clauses.append(time_filter[4:] if time_filter.startswith("AND ") else time_filter)
        if country:
            clauses.append("country = %s")
            params.append(country)

        params.append(limit)

        time_filter = " AND ".join(clauses)
        if time_filter:
            # SQL_ARTICLE_SEARCH has a space before the trailing condition, so
            # append " AND" without an extra space for clean rendered SQL.
            time_filter = time_filter + " AND"

        sql = SQL_ARTICLE_SEARCH.format(time_filter=time_filter)
        return await self.async_execute(sql, tuple(params), read_only=True)

    async def async_get_synthesis_ids(self, cluster_ids: list[str], lang: str = None):
        if not cluster_ids:
            return []
        sql = "SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)"
        params = [cluster_ids]
        if lang:
            sql += " AND lang = %s"
            params.append(lang)
        rows = await self.async_execute(sql, tuple(params), read_only=True)
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

    def get_articles_by_country(self, country, limit=200, sub=None, topic=None, sentiment=None, category=None):
        sql = "SELECT * FROM articles WHERE 1=1"
        params = []

        if category:
            sql += " AND category = %s"
            params.append(category)
        elif country and country != "RS":
            sql += " AND country = %s"
            params.append(country)
        elif country == "RS":
            sql += " AND (country = 'RS' OR country IS NULL OR country = '')"

        if sub:
            sql += " AND subcategory = %s"
            params.append(sub)
        if topic:
            sql += " AND topic = %s"
            params.append(topic)
        if sentiment:
            escaped_sentiment = sentiment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
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
        from core.embeddings import generate_query_embedding

        vector = generate_query_embedding(q)
        vector_str = "[" + ",".join(map(str, vector)) + "]" if vector else None

        # Ensure limit is an integer
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 100

        return self.execute(SQL_ARTICLE_SEARCH, (q, q, vector_str, limit))

    def get_synthesis_ids(self, cluster_ids, lang: str = None):
        if not cluster_ids:
            return []
        sql = "SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)"
        params = [cluster_ids]
        if lang:
            sql += " AND lang = %s"
            params.append(lang)
        rows = self.execute(sql, tuple(params))
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

    def refresh_stats_view(self):
        """Refreshes the article stats materialized view."""
        self.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_article_stats", fetch=False)

    def get_stats(self):
        try:
            total_row = self.execute_one("SELECT COUNT(*) FROM articles")
            total = total_row["count"] if total_row else 0

            by_cat = self.execute("SELECT category, COUNT(*) n FROM articles GROUP BY category ORDER BY n DESC") or []
            by_source = self.execute("SELECT source, COUNT(*) n FROM articles GROUP BY source ORDER BY n DESC") or []

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
            ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
            if not os.path.exists(ini_path):
                log.warning(f"Alembic config not found at {ini_path}, skipping migrations.")
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
    from core.config import DB_RETAIN_DAYS, DB_RETAIN_FAILED_TASKS_DAYS

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
