"""매일 오전 10시 브리핑 — 논문 + AI 뉴스 수집 후 Notion에 저장."""

import os
from datetime import date

from tools.papers import fetch_arxiv_papers, fetch_hf_daily_papers
from tools.search import search_web


async def run_morning_briefing() -> None:
    """매일 10:00 실행. HF + ArXiv 논문과 AI 뉴스를 수집해 Notion에 저장한다."""
    today = date.today().strftime("%Y-%m-%d")
    print(f"[브리핑] {today} 시작...")

    hf_papers = fetch_hf_daily_papers(max_results=5)
    arxiv_papers = fetch_arxiv_papers(query="large language model", max_results=3)
    ai_news = search_web("AI LLM 최신 뉴스", max_results=3)

    content = f"""## Hugging Face 인기 논문

{hf_papers}

## ArXiv 최신 LLM 논문

{arxiv_papers}

## AI 뉴스

{ai_news}
"""
    title = f"아침 브리핑 {today}"

    parent_page_id = os.getenv("NOTION_BRIEFING_PARENT_PAGE_ID")
    if parent_page_id:
        try:
            from tools.notion_tools import create_notion_page, search_notion

            # 오늘 브리핑이 이미 있으면 생성 스킵
            existing = search_notion(title)
            if title in existing:
                print(f"[브리핑] {today} 이미 존재, 스킵")
                return

            result = create_notion_page(title=title, content=content, parent_page_id=parent_page_id)
            print(f"[브리핑] {today} 완료 — {result}")
        except Exception as e:
            print(f"[브리핑] Notion 생성 실패: {e}")
    else:
        print(f"[브리핑] NOTION_BRIEFING_PARENT_PAGE_ID 미설정, 저장 건너뜀")
