"""장기 기억 툴 — 사용자 정보와 선호도를 DB에 저장한다."""

from storage.db import PH, get_conn


def save_memory(key: str, value: str) -> str:
    """사용자 정보나 선호도를 장기 기억에 저장한다. 나중에 다시 참조할 정보에 사용."""
    with get_conn() as con:
        if PH == "%s":
            con.execute(
                "INSERT INTO memories (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                (key, value),
            )
        else:
            con.execute(
                "INSERT INTO memories (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
    return f"기억 저장 완료: {key} = {value}"


def get_memory(key: str) -> str:
    """저장된 특정 기억을 조회한다."""
    with get_conn() as con:
        row = con.execute(f"SELECT value FROM memories WHERE key = {PH}", (key,)).fetchone()
    return row["value"] if row else f"'{key}'에 대한 기억이 없습니다."


def list_memories() -> str:
    """저장된 모든 기억 목록을 반환한다."""
    with get_conn() as con:
        rows = con.execute("SELECT key, value FROM memories ORDER BY key").fetchall()
    if not rows:
        return "저장된 기억이 없습니다."
    return "\n".join(f"- **{r['key']}**: {r['value']}" for r in rows)


def delete_memory(key: str) -> str:
    """저장된 특정 기억을 삭제한다."""
    with get_conn() as con:
        cur = con.execute(f"DELETE FROM memories WHERE key = {PH}", (key,))
        deleted = cur.rowcount if hasattr(cur, "rowcount") else 1
    if not deleted:
        return f"'{key}'에 대한 기억이 없습니다."
    return f"기억 삭제 완료: {key}"
