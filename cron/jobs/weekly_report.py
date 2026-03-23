"""매주 금요일 오후 5시 주간 리포트 — 이번 주 메모를 정리해 저장한다."""

from datetime import date, timedelta

from tools.cost_tracker import get_cost_summary
from tools.notes import create_note, list_notes_raw


async def run_weekly_report() -> None:
    """매주 금요일 17:00 실행. 이번 주 메모 목록과 비용을 정리해 주간 리포트를 생성한다."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_label = week_start.strftime("%Y-%m-%d")
    print(f"[주간 리포트] {week_label} 주 시작...")

    recent_notes = list_notes_raw(limit=30)
    cost_summary = get_cost_summary()

    note_lines = "\n".join(f"- **{n['title']}** (태그: {n['tags']}) — {n['created_at']}" for n in recent_notes)

    content = f"""# 주간 리포트 — {week_label} 주

## 이번 주 저장한 메모 ({len(recent_notes)}개)

{note_lines if note_lines else "기록 없음"}

## 이번 달 API 비용

{cost_summary}
"""
    create_note(
        title=f"주간 리포트 {week_label}",
        content=content,
        tags="주간리포트",
    )
    print(f"[주간 리포트] {week_label} 완료")
