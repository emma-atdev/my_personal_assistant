"""Tavily 웹 검색 툴."""

import os
from functools import lru_cache

from tavily import TavilyClient


@lru_cache(maxsize=1)
def _get_client() -> TavilyClient:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY가 설정되지 않았습니다.")
    return TavilyClient(api_key=api_key)


def search_web(query: str, max_results: int = 5) -> str:
    """웹에서 정보를 검색한다. 최신 정보 조회나 사실 확인이 필요할 때 사용."""
    try:
        client = _get_client()
    except RuntimeError as e:
        return str(e)

    results = client.search(query, max_results=max_results)

    output: list[str] = []
    for r in results.get("results", []):
        output.append(f"**{r['title']}**\n{r['url']}\n{r.get('content', '')[:400]}")

    return "\n\n---\n\n".join(output) if output else "검색 결과가 없습니다."
