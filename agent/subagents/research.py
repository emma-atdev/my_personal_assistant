"""리서치 서브에이전트 — 웹 검색과 논문 수집 전담."""

from langchain.chat_models import init_chat_model

from tools.papers import fetch_arxiv_papers, fetch_hf_daily_papers, fetch_pwc_trending
from tools.search import search_web

RESEARCH_SUBAGENT: dict[str, object] = {
    "name": "research",
    "description": (
        "웹 검색, AI 뉴스 조회, LLM 논문 탐색이 필요할 때 사용. "
        "최신 정보 확인, ArXiv/HuggingFace 논문 수집 담당."
    ),
    "system_prompt": (
        "당신은 AI 리서치 전문가입니다. "
        "웹 검색과 논문 수집을 통해 정확하고 최신 정보를 제공합니다. "
        "결과는 항상 한국어로 요약해 주세요. "
        "논문은 제목, 링크, 핵심 기여점 위주로 정리하세요."
    ),
    "tools": [search_web, fetch_hf_daily_papers, fetch_arxiv_papers, fetch_pwc_trending],
    "model": init_chat_model("openai:gpt-4o-mini"),
}
