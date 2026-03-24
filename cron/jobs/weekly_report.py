"""매주 금요일 오후 5시 주간 리포트 — API 비용을 정리해 Notion에 저장한다."""

import os
from datetime import date, timedelta

from tools.cost_tracker import get_cost_summary


async def run_weekly_report() -> None:
    """매주 금요일 17:00 실행. API 비용 요약을 주간 리포트로 Notion에 저장한다."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_label = week_start.strftime("%Y-%m-%d")
    print(f"[주간 리포트] {week_label} 주 시작...")

    cost_summary = get_cost_summary()

    content = f"""## 이번 달 API 비용

{cost_summary}
"""
    title = f"주간 리포트 {week_label}"

    parent_page_id = os.getenv("NOTION_REPORT_PARENT_PAGE_ID")
    if parent_page_id:
        try:
            from tools.notion_tools import create_notion_page, search_notion

            existing = search_notion(title)
            if title in existing:
                print(f"[주간 리포트] {week_label} 이미 존재, 스킵")
                return

            result = create_notion_page(title=title, content=content, parent_page_id=parent_page_id)
            print(f"[주간 리포트] {week_label} 완료 — {result}")
        except Exception as e:
            print(f"[주간 리포트] Notion 생성 실패: {e}")
    else:
        print("[주간 리포트] NOTION_REPORT_PARENT_PAGE_ID 미설정, 저장 건너뜀")
