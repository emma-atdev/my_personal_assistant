"""크론잡 영구 저장 — DB CRUD."""

from typing import Any

from storage.db import PH, get_conn, now_kst

_MAX_CONSECUTIVE_ERRORS = 3


def save_cron_job(
    job_id: str,
    task: str,
    schedule_kind: str,
    schedule_expr: str,
    tz: str = "Asia/Seoul",
    timeout_seconds: int = 300,
) -> None:
    """크론잡을 DB에 저장한다."""
    now = now_kst()
    with get_conn() as con:
        if PH == "%s":
            con.execute(
                "INSERT INTO cron_jobs (job_id, task, schedule_kind, schedule_expr, tz, timeout_seconds, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (job_id) DO UPDATE SET task = EXCLUDED.task, schedule_kind = EXCLUDED.schedule_kind, "
                "schedule_expr = EXCLUDED.schedule_expr, tz = EXCLUDED.tz, timeout_seconds = EXCLUDED.timeout_seconds",
                (job_id, task, schedule_kind, schedule_expr, tz, timeout_seconds, now),
            )
        else:
            con.execute(
                "INSERT INTO cron_jobs (job_id, task, schedule_kind, schedule_expr, tz, timeout_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET task = excluded.task, schedule_kind = excluded.schedule_kind, "
                "schedule_expr = excluded.schedule_expr, tz = excluded.tz, timeout_seconds = excluded.timeout_seconds",
                (job_id, task, schedule_kind, schedule_expr, tz, timeout_seconds, now),
            )


def load_cron_jobs() -> list[dict[str, Any]]:
    """저장된 모든 크론잡을 반환한다."""
    with get_conn() as con:
        rows = con.execute(
            "SELECT job_id, task, schedule_kind, schedule_expr, tz, enabled, consecutive_errors, timeout_seconds "
            "FROM cron_jobs ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows] if rows else []


def delete_cron_job(job_id: str) -> bool:
    """크론잡을 DB에서 삭제한다. 삭제 성공 여부를 반환한다."""
    with get_conn() as con:
        cur = con.execute(f"DELETE FROM cron_jobs WHERE job_id = {PH}", (job_id,))
        return bool(getattr(cur, "rowcount", 1))


def increment_error(job_id: str) -> int:
    """연속 실패 횟수를 1 증가시키고 현재 값을 반환한다. 임계값 초과 시 자동 비활성화."""
    with get_conn() as con:
        con.execute(
            f"UPDATE cron_jobs SET consecutive_errors = consecutive_errors + 1 WHERE job_id = {PH}",
            (job_id,),
        )
        row = con.execute(f"SELECT consecutive_errors FROM cron_jobs WHERE job_id = {PH}", (job_id,)).fetchone()
        count: int = row["consecutive_errors"] if row else 0
        if count >= _MAX_CONSECUTIVE_ERRORS:
            con.execute(f"UPDATE cron_jobs SET enabled = 0 WHERE job_id = {PH}", (job_id,))
    return count


def reset_errors(job_id: str) -> None:
    """연속 실패 횟수를 0으로 초기화한다."""
    with get_conn() as con:
        con.execute(f"UPDATE cron_jobs SET consecutive_errors = 0 WHERE job_id = {PH}", (job_id,))
