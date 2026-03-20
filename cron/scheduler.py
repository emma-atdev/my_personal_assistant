"""APScheduler 크론잡 설정."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from cron.jobs.morning_briefing import run_morning_briefing
from cron.jobs.weekly_report import run_weekly_report

_scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def setup_scheduler() -> AsyncIOScheduler:
    """크론잡을 등록하고 스케줄러를 반환한다."""
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
