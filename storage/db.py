"""데이터베이스 연결 추상화 — 로컬: SQLite, Railway: PostgreSQL."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

DATABASE_URL = os.getenv("DATABASE_URL")
IS_PG = bool(DATABASE_URL)
PH = "%s" if IS_PG else "?"  # SQL 플레이스홀더

_INITIALIZED = False


def _init_tables_pg(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         SERIAL PRIMARY KEY,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                tags       TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cost_logs (
                id            SERIAL PRIMARY KEY,
                date          TIMESTAMP DEFAULT NOW(),
                model         TEXT NOT NULL,
                input_tokens  INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd      NUMERIC(12, 6) NOT NULL
            )
        """)
    conn.commit()


def _init_tables_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            content    TEXT NOT NULL,
            tags       TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cost_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT DEFAULT (datetime('now', 'localtime')),
            model         TEXT NOT NULL,
            input_tokens  INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd      REAL NOT NULL
        )
    """)
    conn.commit()


@contextmanager
def get_conn() -> Generator[Any, None, None]:
    """DATABASE_URL 유무에 따라 PostgreSQL 또는 SQLite 연결을 반환한다."""
    global _INITIALIZED

    if IS_PG:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        if not _INITIALIZED:
            _init_tables_pg(conn)
            _INITIALIZED = True
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        db_path = Path("storage/notes.db")
        db_path.parent.mkdir(exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        if not _INITIALIZED:
            _init_tables_sqlite(conn)
            _INITIALIZED = True
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()