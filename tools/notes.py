"""노트 CRUD 툴 — SQLite(로컬) / PostgreSQL(Railway) 기반 메모 저장소."""

from datetime import datetime
from typing import Any

from storage.db import PH, get_conn


def create_note(title: str, content: str, tags: str = "") -> str:
    """새 메모를 저장한다. 정보 기록, 논문 노트, 아이디어 저장에 사용."""
    with get_conn() as con:
        if PH == "%s":
            # PostgreSQL: RETURNING으로 id 반환
            cur = con.execute(
                "INSERT INTO notes (title, content, tags) VALUES (%s, %s, %s) RETURNING id",
                (title, content, tags),
            )
            row = cur.fetchone()
            note_id = row["id"] if row else "?"
        else:
            # SQLite: lastrowid로 id 확인
            cur = con.execute(
                "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
                (title, content, tags),
            )
            note_id = cur.lastrowid
    return f"메모 저장 완료 (ID: {note_id}) — {title}"


def get_note(note_id: int) -> str:
    """ID로 특정 메모를 조회한다."""
    with get_conn() as con:
        row = con.execute(f"SELECT * FROM notes WHERE id = {PH}", (note_id,)).fetchone()
    if not row:
        return f"ID {note_id}인 메모를 찾을 수 없습니다."
    return (
        f"# {row['title']} (ID: {row['id']})\n"
        f"태그: {row['tags']}\n"
        f"작성: {row['created_at']}\n\n"
        f"{row['content']}"
    )


def list_notes(limit: int = 20) -> str:
    """최근 메모 목록을 반환한다."""
    with get_conn() as con:
        rows = con.execute(
            f"SELECT id, title, tags, created_at FROM notes ORDER BY id DESC LIMIT {PH}",
            (limit,),
        ).fetchall()
    if not rows:
        return "저장된 메모가 없습니다."
    lines = [f"**ID {r['id']}** | {r['title']} | {r['tags']} | {r['created_at']}" for r in rows]
    return "\n".join(lines)


def list_notes_raw(limit: int = 20) -> list[dict[str, Any]]:
    """최근 메모를 dict 리스트로 반환한다 (내부 사용)."""
    with get_conn() as con:
        rows = con.execute(
            f"SELECT id, title, tags, created_at FROM notes ORDER BY id DESC LIMIT {PH}",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def search_notes(query: str, limit: int = 5) -> str:
    """제목이나 내용에서 메모를 검색한다. 과거에 저장한 정보를 찾을 때 사용."""
    like = f"%{query}%"
    with get_conn() as con:
        rows = con.execute(
            f"""
            SELECT id, title, tags, created_at FROM notes
            WHERE title LIKE {PH} OR content LIKE {PH} OR tags LIKE {PH}
            ORDER BY id DESC LIMIT {PH}
            """,
            (like, like, like, limit),
        ).fetchall()
    if not rows:
        return f"'{query}'에 대한 검색 결과가 없습니다."
    lines = [f"**ID {r['id']}** | {r['title']} | {r['tags']} | {r['created_at']}" for r in rows]
    return "\n".join(lines)


def update_note(note_id: int, content: str) -> str:
    """기존 메모 내용을 수정한다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute(
            f"UPDATE notes SET content = {PH}, updated_at = {PH} WHERE id = {PH}",
            (content, now, note_id),
        )
    return f"메모 수정 완료 (ID: {note_id})"


def delete_note(note_id: int) -> str:
    """메모를 삭제한다."""
    with get_conn() as con:
        con.execute(f"DELETE FROM notes WHERE id = {PH}", (note_id,))
    return f"메모 삭제 완료 (ID: {note_id})"
