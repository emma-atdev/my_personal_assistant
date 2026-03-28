"""데이터베이스 연결 추상화 — 로컬, Neon: PostgreSQL (로컬 SQLite 가능)."""

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> str:
    """현재 KST 시각을 DB 저장용 문자열로 반환한다."""
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


DATABASE_URL = os.getenv("DATABASE_URL")
IS_PG = bool(DATABASE_URL)
PH = "%s" if IS_PG else "?"  # SQL 플레이스홀더

_INITIALIZED = False


def _init_tables_pg(conn: Any) -> None:
    with conn.cursor() as cur:
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                thread_id  TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT '새 채팅',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata   TEXT NOT NULL DEFAULT '{}'
            )
        """)
        cur.execute("""
            ALTER TABLE conversations ADD COLUMN IF NOT EXISTS metadata TEXT NOT NULL DEFAULT '{}'
        """)
        cur.execute("""
            ALTER TABLE conversations ADD COLUMN IF NOT EXISTS context_tokens INTEGER NOT NULL DEFAULT 0
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                job_id             TEXT PRIMARY KEY,
                task               TEXT NOT NULL,
                schedule_kind      TEXT NOT NULL,
                schedule_expr      TEXT NOT NULL,
                tz                 TEXT NOT NULL DEFAULT 'Asia/Seoul',
                enabled            BOOLEAN NOT NULL DEFAULT TRUE,
                consecutive_errors INTEGER NOT NULL DEFAULT 0,
                timeout_seconds    INTEGER NOT NULL DEFAULT 300,
                created_at         TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()


def _init_tables_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            thread_id  TEXT PRIMARY KEY,
            title      TEXT NOT NULL DEFAULT '새 대화',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            metadata   TEXT NOT NULL DEFAULT '{}'
        )
    """)
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
    except Exception:  # noqa: BLE001
        pass  # 이미 존재하면 무시
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 0")
    except Exception:  # noqa: BLE001
        pass
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            job_id             TEXT PRIMARY KEY,
            task               TEXT NOT NULL,
            schedule_kind      TEXT NOT NULL,
            schedule_expr      TEXT NOT NULL,
            tz                 TEXT NOT NULL DEFAULT 'Asia/Seoul',
            enabled            INTEGER NOT NULL DEFAULT 1,
            consecutive_errors INTEGER NOT NULL DEFAULT 0,
            timeout_seconds    INTEGER NOT NULL DEFAULT 300,
            created_at         TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()


class _PgConnWrapper:
    """psycopg2 connection을 SQLite처럼 con.execute()로 쓸 수 있게 감싼다."""

    def __init__(self, conn: Any) -> None:
        import psycopg2.extras

        self._conn = conn
        self._cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, sql: str, params: Any = None) -> Any:
        self._cur.execute(sql, params)
        return self._cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._cur.close()
        self._conn.close()


@contextmanager
def get_conn() -> Generator[Any]:
    """DATABASE_URL 유무에 따라 PostgreSQL 또는 SQLite 연결을 반환한다."""
    global _INITIALIZED

    if IS_PG:
        import psycopg2

        raw_conn = psycopg2.connect(DATABASE_URL)
        if not _INITIALIZED:
            _init_tables_pg(raw_conn)
            _INITIALIZED = True
        conn = _PgConnWrapper(raw_conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        db_path = Path("storage/data.db")
        db_path.parent.mkdir(exist_ok=True)
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_conn.row_factory = sqlite3.Row
        if not _INITIALIZED:
            _init_tables_sqlite(sqlite_conn)
            _INITIALIZED = True
        try:
            yield sqlite_conn
            sqlite_conn.commit()
        except Exception:
            sqlite_conn.rollback()
            raise
        finally:
            sqlite_conn.close()
