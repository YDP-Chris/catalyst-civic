#!/usr/bin/env python
"""
Shared PostgreSQL connection helper for the Insight Engine.

Mirrors the connection convention used across the Catalyst Civic pipelines:
direct psycopg2 against the local `catalyst_civic` database, configured via
PG_* environment variables. No ORM, no pooling — one short-lived connection
per run, same as the push scripts.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

try:
    import psycopg2
    import psycopg2.extras
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "Missing dependency: psycopg2. Install with "
        "`pip install psycopg2-binary` (or `py -m pip install psycopg2-binary` on Windows)."
    ) from exc


PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DB = os.getenv("PG_DB", "catalyst_civic")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "postgres")


def connect():
    """Open a new psycopg2 connection using the standard PG_* env vars."""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )


@contextmanager
def cursor(dict_rows: bool = True) -> Iterator["psycopg2.extensions.cursor"]:
    """
    Context manager yielding a cursor with automatic commit/rollback + close.

    By default returns RealDictCursor rows (dict access by column name), which
    keeps the lens queries readable. Pass dict_rows=False for tuple rows.
    """
    conn = connect()
    factory = psycopg2.extras.RealDictCursor if dict_rows else None
    cur = conn.cursor(cursor_factory=factory)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
