"""APScheduler 크론잡 설정."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from cron.jobs.morning_briefing import run_morning_briefing
from cron.jobs.weekly_report import run_weekly_report

_scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def get_scheduler() -> AsyncIOScheduler:
    """스케줄러 싱글턴을 반환한다."""
    return _scheduler


def setup_scheduler() -> AsyncIOScheduler:
    """기본 크론잡을 등록하고 스케줄러를 반환한다."""
    _scheduler.add_job(
        run_morning_briefing,
        CronTrigger(hour=10, minute=0, timezone="Asia/Seoul"),
        id="morning_briefing",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_weekly_report,
        CronTrigger(day_of_week="fri", hour=17, minute=0, timezone="Asia/Seoul"),
        id="weekly_report",
        replace_existing=True,
    )
    return _scheduler


def _build_trigger(schedule_kind: str, schedule_expr: str, tz: str) -> CronTrigger | IntervalTrigger | DateTrigger:
    if schedule_kind == "cron":
        parts = schedule_expr.split()
        if len(parts) != 5:  # noqa: PLR2004
            raise ValueError(f"cron 표현식은 5개 필드여야 합니다: {schedule_expr!r}")
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz,
        )
    elif schedule_kind == "every":
        seconds = int(schedule_expr) // 1000
        return IntervalTrigger(seconds=seconds)
    elif schedule_kind == "at":
        return DateTrigger(run_date=schedule_expr, timezone=tz)
    else:
        raise ValueError(f"알 수 없는 schedule_kind: {schedule_kind!r}")


def add_user_job(
    job_id: str,
    task: str,
    schedule_kind: str,
    schedule_expr: str,
    tz: str = "Asia/Seoul",
    timeout_seconds: int = 300,
) -> None:
    """사용자 정의 크론잡을 스케줄러에 동적으로 등록한다."""
    from cron.jobs.user_job import run_user_job

    trigger = _build_trigger(schedule_kind, schedule_expr, tz)
    _scheduler.add_job(
        run_user_job,
        trigger,
        id=f"user_{job_id}",
        kwargs={"job_id": job_id, "task": task, "timeout_seconds": timeout_seconds},
        replace_existing=True,
    )


def remove_user_job(job_id: str) -> None:
    """스케줄러에서 사용자 정의 크론잡을 제거한다."""
    apscheduler_id = f"user_{job_id}"
    if _scheduler.get_job(apscheduler_id):
        _scheduler.remove_job(apscheduler_id)


def load_user_jobs_from_db() -> None:
    """DB에 저장된 사용자 크론잡을 스케줄러에 복원한다. FastAPI lifespan에서 호출."""
    from storage.cron_jobs import load_cron_jobs

    for job in load_cron_jobs():
        if not job["enabled"]:
            continue
        try:
            add_user_job(
                job_id=job["job_id"],
                task=job["task"],
                schedule_kind=job["schedule_kind"],
                schedule_expr=job["schedule_expr"],
                tz=job["tz"],
                timeout_seconds=job["timeout_seconds"],
            )
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] 잡 복원 실패 {job['job_id']}: {e}")
