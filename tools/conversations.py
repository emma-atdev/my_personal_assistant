"""대화 세션 관리 툴 — 목록 조회, 생성, 제목 수정, 삭제."""

import uuid
from typing import Any

from storage.db import PH, get_conn, now_kst


def create_conversation(title: str = "새 대화") -> str:
    """새 대화 세션을 생성하고 thread_id를 반환한다."""
    thread_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO conversations (thread_id, title, created_at, updated_at) VALUES ({PH}, {PH}, {PH}, {PH})",
            (thread_id, title, now_kst(), now_kst()),
        )
    return thread_id


def list_conversations(limit: int = 30) -> list[dict[str, Any]]:
    """최근 대화 목록을 반환한다."""
    with get_conn() as conn:
        cur = conn.execute(
            f"SELECT thread_id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT {PH}",
            (limit,),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_conversation_title(thread_id: str, title: str) -> None:
    """대화 제목을 업데이트한다."""
    with get_conn() as conn:
        conn.execute(
            f"UPDATE conversations SET title={PH}, updated_at={PH} WHERE thread_id={PH}",
            (title, now_kst(), thread_id),
        )


def touch_conversation(thread_id: str) -> None:
    """대화의 updated_at을 갱신한다 (최근 대화 정렬용)."""
    with get_conn() as conn:
        conn.execute(
            f"UPDATE conversations SET updated_at={PH} WHERE thread_id={PH}",
            (now_kst(), thread_id),
        )


def delete_conversation(thread_id: str) -> None:
    """대화 세션과 LangGraph 체크포인트 데이터를 삭제한다."""
    from storage.db import IS_PG

    with get_conn() as conn:
        conn.execute(
            f"DELETE FROM conversations WHERE thread_id={PH}",
            (thread_id,),
        )
        if IS_PG:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                conn.execute(
                    f"DELETE FROM {table} WHERE thread_id={PH}",
                    (thread_id,),
                )
