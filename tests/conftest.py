"""테스트 공통 픽스처 — 임시 SQLite DB를 사용해 실제 DB를 건드리지 않는다."""

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

# 에이전트 모듈 임포트 시 OpenAI 클라이언트가 초기화되므로 더미 키 설정
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")


@pytest.fixture(autouse=True)
def use_test_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """각 테스트마다 임시 SQLite DB를 사용한다."""
    import storage.db as db_module

    db_file = tmp_path / "test.db"

    monkeypatch.setattr(db_module, "DATABASE_URL", None)
    monkeypatch.setattr(db_module, "IS_PG", False)
    monkeypatch.setattr(db_module, "PH", "?")
    monkeypatch.setattr(db_module, "_INITIALIZED", False)

    @contextmanager
    def _test_get_conn() -> Generator[Any]:
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        if not db_module._INITIALIZED:
            db_module._init_tables_sqlite(conn)
            db_module._INITIALIZED = True
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(db_module, "get_conn", _test_get_conn)

    for module_path in [
        "tools.memory",
        "tools.cost_tracker",
    ]:
        import importlib

        mod = importlib.import_module(module_path)
        monkeypatch.setattr(mod, "get_conn", _test_get_conn)
        monkeypatch.setattr(mod, "PH", "?")
