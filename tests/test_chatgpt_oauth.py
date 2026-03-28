"""ChatGPT OAuth 클라이언트 테스트.

Unit 테스트: httpx 응답을 mock해서 실제 API 호출 없이 실행.
Integration 테스트: CHATGPT_SESSION_TOKEN 환경변수가 설정된 경우에만 실행.
    uv run pytest tests/test_chatgpt_oauth.py -v -k integration
"""

import json
import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth.chatgpt_oauth import ChatGPTAPIError, ChatGPTAuthError, ChatGPTOAuthClient

# ── Unit 테스트 ──────────────────────────────────────────────


def _mock_session_response(access_token: str = "test-token-abc") -> MagicMock:
    """세션 엔드포인트 응답 mock을 반환한다."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"accessToken": access_token, "user": {"id": "user-123"}}
    return resp


def _sse_lines(parts: list[str]) -> list[str]:
    """SSE 이벤트 라인 목록을 생성한다."""
    lines = []
    for part in parts:
        event = {"message": {"content": {"parts": [part]}}}
        lines.append(f"data: {json.dumps(event)}")
    lines.append("data: [DONE]")
    return lines


class TestRefreshToken:
    async def test_성공(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_session_response("my-access-token")
            token = await client.refresh_token()
        assert token == "my-access-token"
        assert client._access_token == "my-access-token"

    async def test_세션_토큰_없음(self) -> None:
        client = ChatGPTOAuthClient(session_token="")
        with pytest.raises(ChatGPTAuthError, match="CHATGPT_SESSION_TOKEN"):
            await client.refresh_token()

    async def test_401_응답(self) -> None:
        client = ChatGPTOAuthClient(session_token="expired-session")
        resp = MagicMock()
        resp.status_code = 401
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChatGPTAuthError, match="만료"):
                await client.refresh_token()

    async def test_비정상_응답(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        resp = MagicMock()
        resp.status_code = 500
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChatGPTAPIError, match="500"):
                await client.refresh_token()

    async def test_accessToken_없는_응답(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}  # accessToken 없음
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(ChatGPTAuthError, match="accessToken"):
                await client.refresh_token()


def _sse_chunks(parts: list[str]) -> list[bytes]:
    """SSE 이벤트를 bytes chunk 목록으로 반환한다 (curl_cffi aiter_content 방식)."""
    lines = _sse_lines(parts)
    return [("\n".join(lines) + "\n").encode()]


class TestSendMessage:
    async def test_성공(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        client._access_token = "pre-set-token"

        async def mock_aiter_content() -> AsyncGenerator[bytes]:
            for chunk in _sse_chunks(["안녕", "안녕하세요", "안녕하세요!"]):
                yield chunk

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.aiter_content = mock_aiter_content

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.send_message("안녕")

        # 마지막 누적 텍스트
        assert result == "안녕하세요!"

    async def test_403_에러(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        client._access_token = "pre-set-token"

        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(ChatGPTAPIError, match="403"):
                await client.send_message("테스트")

    async def test_429_rate_limit(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        client._access_token = "pre-set-token"

        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(ChatGPTAPIError, match="429"):
                await client.send_message("테스트")


class TestHealthCheck:
    async def test_정상(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        with (
            patch.object(client, "refresh_token", new_callable=AsyncMock, return_value="abc-token-123"),
            patch.object(client, "send_message", new_callable=AsyncMock, return_value="OK"),
        ):
            result = await client.health_check()

        assert result["ok"] is True
        assert result["error"] is None

    async def test_인증_실패(self) -> None:
        client = ChatGPTOAuthClient(session_token="bad-token")
        with patch.object(
            client,
            "refresh_token",
            new_callable=AsyncMock,
            side_effect=ChatGPTAuthError("만료"),
        ):
            result = await client.health_check()

        assert result["ok"] is False
        assert "인증 오류" in result["error"]

    async def test_api_실패(self) -> None:
        client = ChatGPTOAuthClient(session_token="valid-session")
        with (
            patch.object(client, "refresh_token", new_callable=AsyncMock, return_value="token"),
            patch.object(
                client,
                "send_message",
                new_callable=AsyncMock,
                side_effect=ChatGPTAPIError("403"),
            ),
        ):
            result = await client.health_check()

        assert result["ok"] is False
        assert "API 오류" in result["error"]


# ── Integration 테스트 (실제 API 호출) ──────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("CHATGPT_SESSION_TOKEN"),
    reason="CHATGPT_SESSION_TOKEN 환경변수 필요",
)
class TestIntegration:
    async def test_토큰_갱신(self) -> None:
        async with ChatGPTOAuthClient() as client:
            token = await client.refresh_token()
        assert token and len(token) > 20

    async def test_메시지_전송(self) -> None:
        async with ChatGPTOAuthClient() as client:
            response = await client.send_message("respond with exactly the word: PONG")
        assert response.strip()
        print(f"\n실제 응답: {response[:100]}")

    async def test_헬스체크(self) -> None:
        async with ChatGPTOAuthClient() as client:
            result = await client.health_check()
        print(f"\n헬스체크 결과: {result}")
        assert result["ok"] is True, f"헬스체크 실패: {result['error']}"
