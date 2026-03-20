"""매일 오전 10시 브리핑 — 논문 + AI 뉴스 수집 후 메모로 저장."""

from datetime import date

from tools.notes import create_note
from tools.papers import fetch_arxiv_papers, fetch_hf_daily_papers
from tools.search import search_web


async def run_morning_briefing() -> None:
    """매일 10:00 실행. HF + ArXiv 논문과 AI 뉴스를 수집해 메모로 저장한다."""
    today = date.today().strftime("%Y-%m-%d")
    print(f"[브리핑] {today} 시작...")

    hf_papers = fetch_hf_daily_papers(max_results=5)
    arxiv_papers = fetch_arxiv_papers(query="large language model", max_results=3)
    ai_news = search_web("AI LLM 최신 뉴스", max_results=3)

    content = f"""# 아침 브리핑 — {today}

## Hugging Face 인기 논문

{hf_papers}

## ArXiv 최신 LLM 논문

{arxiv_papers}

## AI 뉴스

{ai_news}
"""
    create_note(
        title=f"아침 브리핑 {today}",
        content=content,
        tags="브리핑,논문,뉴스",
    )
    print(f"[브리핑] {today} 완료")
