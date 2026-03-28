"""크론잡 관리 툴 — 오케스트레이터에서 사용자 정의 크론잡을 등록·조회·삭제한다."""

from uuid import uuid4


def register_cron_job(
    task: str,
    schedule_kind: str,
    schedule_expr: str,
    tz: str = "Asia/Seoul",
    timeout_seconds: int = 300,
) -> str:
    """사용자 정의 크론잡을 등록한다. HITL 대상 — 실행 전 사용자 확인 필요.

    Args:
        task: 실행할 작업 설명 (예: "오늘의 AI 뉴스 브리핑 해줘")
        schedule_kind: 스케줄 종류
            - "cron": cron 표현식 반복 (예: "0 9 * * *" = 매일 오전 9시)
            - "every": 인터벌 반복, schedule_expr은 밀리초 문자열 (예: "3600000" = 1시간마다)
            - "at": 단발 실행, schedule_expr은 ISO 8601 (예: "2026-04-01T09:00:00")
        schedule_expr: 스케줄 표현식 (schedule_kind에 따라 형식 다름)
        tz: 타임존 (기본: "Asia/Seoul")
        timeout_seconds: 실행 제한 시간 초 (기본: 300)
    """
    from cron.scheduler import add_user_job
    from storage.cron_jobs import save_cron_job

    job_id = str(uuid4())
    save_cron_job(job_id, task, schedule_kind, schedule_expr, tz, timeout_seconds)
    add_user_job(job_id, task, schedule_kind, schedule_expr, tz, timeout_seconds)
    if schedule_kind == "every":
        kind_label = f"{int(schedule_expr) // 1000}초마다"
    elif schedule_kind == "cron":
        kind_label = f"반복 ({schedule_expr})"
    else:
        kind_label = f"{schedule_expr} 단발"
    return f"크론잡 등록 완료\n- ID: {job_id}\n- 작업: {task}\n- 스케줄: {kind_label}"


def list_cron_jobs() -> str:
    """등록된 크론잡 목록을 반환한다. 시스템 고정 잡과 사용자 정의 잡을 모두 표시한다."""
    from storage.cron_jobs import load_cron_jobs

    lines = ["**시스템 고정 잡:**"]
    lines.append("- **morning_briefing** | 매일 오전 10시 논문·뉴스 브리핑 → Notion 저장\n  스케줄: `0 10 * * *` | ✅ 활성")
    lines.append("- **weekly_report** | 매주 금요일 오후 5시 주간 리포트 → Notion 저장\n  스케줄: `0 17 * * 5` | ✅ 활성")

    jobs = load_cron_jobs()
    if jobs:
        lines.append("\n**사용자 정의 잡:**")
        for j in jobs:
            status = "✅ 활성" if j["enabled"] else f"❌ 비활성 (연속 실패 {j['consecutive_errors']}회)"
            lines.append(
                f"- **{j['job_id'][:8]}...** | {j['task']}\n"
                f"  스케줄: {j['schedule_kind']} `{j['schedule_expr']}` | {status}"
            )
    else:
        lines.append("\n**사용자 정의 잡:** 없음")

    return "\n".join(lines)


def delete_cron_job(job_id: str) -> str:
    """등록된 크론잡을 삭제한다.

    Args:
        job_id: 삭제할 크론잡 ID (list_cron_jobs로 확인)
    """
    from cron.scheduler import remove_user_job
    from storage.cron_jobs import delete_cron_job as _delete

    removed = _delete(job_id)
    if not removed:
        return f"크론잡 '{job_id}'를 찾을 수 없습니다."
    remove_user_job(job_id)
    return f"크론잡 삭제 완료: {job_id}"
