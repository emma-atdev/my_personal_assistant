"""논문 수집 툴 — Hugging Face Daily Papers, ArXiv, Papers with Code."""

from functools import lru_cache

import arxiv
import httpx


@lru_cache(maxsize=1)
def _arxiv_client() -> arxiv.Client:
    return arxiv.Client()


def fetch_hf_daily_papers(max_results: int = 5) -> str:
    """Hugging Face Daily Papers에서 커뮤니티 인기 논문을 가져온다. 오늘 핫한 AI 논문 탐색에 사용."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://huggingface.co/api/daily_papers",
                params={"limit": max_results},
            )
            resp.raise_for_status()
            papers = resp.json()

        output: list[str] = []
        for p in papers[:max_results]:
            paper = p.get("paper", {})
            title = paper.get("title", "제목 없음")
            summary = paper.get("summary", "")[:400]
            paper_id = paper.get("id", "")
            url = f"https://huggingface.co/papers/{paper_id}" if paper_id else ""
            upvotes = paper.get("upvotes", 0)
            github_stars = paper.get("githubStars", 0)
            stats = f"👍 {upvotes}"
            if github_stars:
                stats += f" · ⭐ {github_stars}"
            output.append(f"**{title}**\n{url}\n{stats}\n{summary}...")

        return "\n\n---\n\n".join(output) if output else "논문을 가져올 수 없습니다."
    except httpx.HTTPError as e:
        return f"HF Daily Papers 오류: {e}"


def fetch_arxiv_papers(query: str = "large language model", max_results: int = 5) -> str:
    """ArXiv에서 LLM 관련 최신 논문을 검색한다. cs.CL, cs.AI, cs.LG 카테고리 대상."""
    try:
        client = _arxiv_client()
        search = arxiv.Search(
            query=f"({query}) AND (cat:cs.CL OR cat:cs.AI OR cat:cs.LG)",
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        output: list[str] = []
        for paper in client.results(search):
            authors = ", ".join(str(a) for a in paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " 외"
            output.append(f"**{paper.title}**\n{paper.entry_id}\n저자: {authors}\n{paper.summary[:400]}...")

        return "\n\n---\n\n".join(output) if output else "논문을 찾을 수 없습니다."
    except Exception as e:
        return f"ArXiv 검색 오류: {e}"


