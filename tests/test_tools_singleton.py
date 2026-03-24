"""싱글턴 클라이언트 동작 검증 — 동일 인스턴스 재사용 확인."""

from unittest.mock import MagicMock, patch


def test_search_client_is_singleton(monkeypatch: object) -> None:
    """TavilyClient는 첫 호출 때만 생성되고 이후 재사용된다."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")  # type: ignore[attr-defined]

    from tools.search import _get_client

    _get_client.cache_clear()

    with patch("tools.search.TavilyClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        c1 = _get_client()
        c2 = _get_client()

    assert c1 is c2
    assert mock_cls.call_count == 1


def test_search_client_no_api_key(monkeypatch: object) -> None:
    """API 키 없으면 search_web이 에러 문자열을 반환한다."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)  # type: ignore[attr-defined]

    from tools.search import _get_client, search_web

    _get_client.cache_clear()

    result = search_web("테스트")
    assert "TAVILY_API_KEY" in result


def test_arxiv_client_is_singleton() -> None:
    """arxiv.Client는 첫 호출 때만 생성되고 이후 재사용된다."""
    from tools.papers import _arxiv_client

    _arxiv_client.cache_clear()

    with patch("tools.papers.arxiv.Client") as mock_cls:
        mock_cls.return_value = MagicMock()
        c1 = _arxiv_client()
        c2 = _arxiv_client()

    assert c1 is c2
    assert mock_cls.call_count == 1
