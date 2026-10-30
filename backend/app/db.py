"""Thin psycopg2 connection pool with pgvector + JSON adapters."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, List, Optional

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from psycopg2.pool import ThreadedConnectionPool

from .config import settings

_pool: Optional[ThreadedConnectionPool] = None


def _bootstrap_extensions() -> None:
    # register_vector needs the type to exist, so create it on a plain connection first.
    conn = psycopg2.connect(settings.database_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        conn.close()


def pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _bootstrap_extensions()
        _pool = ThreadedConnectionPool(1, 12, settings.database_url)
    return _pool


@contextmanager
def connect() -> Iterator[Any]:
    p = pool()
    conn = p.getconn()
    try:
        register_vector(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def init_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)


def fetch_all(sql: str, params: Any = None) -> List[dict]:
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_one(sql: str, params: Any = None) -> Optional[dict]:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Any = None) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)


def jsonb(value: Any) -> psycopg2.extras.Json:
    return psycopg2.extras.Json(value, dumps=lambda v: json.dumps(v, default=str))
