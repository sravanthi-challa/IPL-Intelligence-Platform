import sys
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple, Generator
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from psycopg2.errors import QueryCanceled

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "utils"))

from config import AppConfig
from logger import get_logger, LatencyTracker

logger = get_logger("db_connection")

class DatabaseManager:
    """
    Enterprise-grade PostgreSQL connection manager providing connection pooling,
    statement timeouts, query row limit bounds, and connection lifecycle management.
    """
    _pool: Optional[ThreadedConnectionPool] = None

    @classmethod
    def get_pool(cls) -> ThreadedConnectionPool:
        if cls._pool is None:
            db_params = AppConfig.get_db_dict()
            logger.info(f"Initializing PostgreSQL ThreadedConnectionPool ({AppConfig.DB_POOL_MIN}-{AppConfig.DB_POOL_MAX} connections) to {db_params['dbname']}@{db_params['host']}:{db_params['port']}")
            cls._pool = ThreadedConnectionPool(
                minconn=AppConfig.DB_POOL_MIN,
                maxconn=AppConfig.DB_POOL_MAX,
                **db_params
            )
        return cls._pool

    @classmethod
    def close_pool(cls):
        if cls._pool is not None:
            logger.info("Closing PostgreSQL Connection Pool...")
            cls._pool.closeall()
            cls._pool = None

@contextmanager
def get_db_connection() -> Generator[Any, None, None]:
    """
    Context manager that checks out a connection from the pool,
    configures statement_timeout, and safely returns it to the pool on exit.
    """
    pool = DatabaseManager.get_pool()
    conn = pool.getconn()
    try:
        # Enforce statement timeout on connection
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = '{AppConfig.STATEMENT_TIMEOUT_MS}ms';")
        yield conn
    except Exception as exc:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

class PooledConnectionProxy:
    """Proxy around psycopg2 connection that safely puts it back to pool on close()."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def close(self):
        if not self._closed and self._pool:
            try:
                self._pool.putconn(self._conn)
            finally:
                self._closed = True

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def get_db_cursor():
    """
    Backward-compatible cursor helper. Checks out connection, wraps in proxy,
    and returns (proxy, cur). Calling proxy.close() returns the connection to the pool.
    """
    pool = DatabaseManager.get_pool()
    conn = pool.getconn()
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = '{AppConfig.STATEMENT_TIMEOUT_MS}ms';")
    
    proxy = PooledConnectionProxy(conn, pool)
    return proxy, proxy.cursor(cursor_factory=RealDictCursor)

def execute_query(
    sql: str,
    params: Optional[Tuple[Any, ...]] = None,
    max_rows: Optional[int] = None,
    read_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Executes a parameterized SQL query safely with statement timeout,
    row limit caps, and latency logging.
    """
    row_limit = max_rows or AppConfig.MAX_ROWS_LIMIT
    
    # Security check for read-only analytical mode
    if read_only:
        sql_stripped = sql.strip().upper()
        prohibited_verbs = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"]
        for verb in prohibited_verbs:
            if sql_stripped.startswith(verb) or f" {verb} " in sql_stripped:
                raise ValueError(f"Security Alert: Prohibited write verb '{verb}' detected in read-only analytical query.")

    with get_db_connection() as conn:
        with LatencyTracker("sql_query_execution", logger=logger, slow_threshold_ms=300.0):
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(sql, params)
                    if cur.description is None:
                        return []
                    
                    rows = cur.fetchmany(row_limit)
                    return [dict(r) for r in rows]
                except QueryCanceled as qc:
                    logger.error(f"SQL Query timed out after {AppConfig.STATEMENT_TIMEOUT_MS}ms! SQL: {sql[:100]}...")
                    raise TimeoutError(f"Database query execution exceeded limit of {AppConfig.STATEMENT_TIMEOUT_MS}ms.") from qc
