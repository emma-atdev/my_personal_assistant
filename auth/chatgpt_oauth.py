"""ChatGPT 비공개 API OAuth 클라이언트.

ChatGPT Plus 구독을 API 키 없이 활용한다.
공식 API가 아니므로 스펙 변경 시 깨질 수 있음 — health_check()로 상태 확인.

쿠키 추출 방법:
    Chrome DevTools → Application → Cookies → chatgpt.com
    - __Secure-next-auth.session-token (.0 + .1 붙이기) → CHATGPT_SESSION_TOKEN
    - cf_clearance → CHATGPT_CF_CLEARANCE
"""

import base64
import hashlib
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from curl_cffi.requests import AsyncSession

_BASE = "https://chatgpt.com"
_SESSION_URL = f"{_BASE}/api/auth/session"
_SENTINEL_URL = f"{_BASE}/backend-api/sentinel/chat-requirements"
_CONVERSATION_URL = f"{_BASE}/backend-api/conversation"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/event-stream",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://chatgpt.com/",
    "Origin": "https://chatgpt.com",
}


def _solve_pow(seed: str, difficulty: str) -> str:
    """SHA3-512 proof-of-work를 풀고 proof token을 반환한다.

    hash(seed + n)의 앞 len(difficulty) 자리가 difficulty보다 작은 n을 탐색한다.
    """
    n = 0
    while True:
        candidate = f"{seed}{n}".encode()
        h = hashlib.sha3_512(candidate).hexdigest()
        if h[: len(difficulty)] <= difficulty:
            payload = base64.b64encode(json.dumps([seed, n, difficulty, int(time.time() * 1000)]).encode()).decode()
            return f"gAAAAAB{payload}"
        n += 1


class ChatGPTAuthError(Exception):
    """인증 실패 — 세션 토큰 만료 또는 잘못된 토큰."""


class ChatGPTAPIError(Exception):
    """API 응답 오류 — 스펙 변경 또는 rate limit."""


class ChatGPTOAuthClient:
    """ChatGPT 비공개 API 클라이언트."""

    def __init__(
        self,
        session_token: str | None = None,
        cf_clearance: str | None = None,
    ) -> None:
        # None이면 env var 사용, ""이면 명시적으로 빈 값 (테스트용)
        self._session_token = session_token if session_token is not None else os.getenv("CHATGPT_SESSION_TOKEN", "")
        self._cf_clearance = cf_clearance if cf_clearance is not None else os.getenv("CHATGPT_CF_CLEARANCE", "")
        self._access_token: str = ""
        self._pow_token: str = ""
        self._device_id: str = str(uuid.uuid4())
        # Chrome TLS 핑거프린트 impersonation — Cloudflare 우회
        cookies: dict[str, str] = {}
        if self._session_token:
            cookies["__Secure-next-auth.session-token"] = self._session_token
        if self._cf_clearance:
            cookies["cf_clearance"] = self._cf_clearance
        self._client = AsyncSession(
            impersonate="chrome124",
            headers=_HEADERS,
            cookies=cookies,
            timeout=30.0,
        )

    async def __aenter__(self) -> "ChatGPTOAuthClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.close()  # type: ignore[no-untyped-call, unused-ignore]

    async def refresh_token(self) -> str:
        """세션 토큰으로 access token을 갱신한다."""
        if not self._session_token:
            raise ChatGPTAuthError("CHATGPT_SESSION_TOKEN이 설정되지 않았습니다.")

        resp = await self._client.get(_SESSION_URL)

        if resp.status_code == 401:
            raise ChatGPTAuthError("세션 토큰이 만료됐거나 유효하지 않습니다.")
        if resp.status_code != 200:
            raise ChatGPTAPIError(f"세션 엔드포인트 오류: HTTP {resp.status_code}")

        data: dict[str, Any] = resp.json()  # type: ignore[no-untyped-call]
        token: str | None = data.get("accessToken")
        if not token:
            raise ChatGPTAuthError("accessToken을 가져올 수 없습니다. 세션 토큰을 확인하세요.")

        self._access_token = token
        return token

    async def _ensure_token(self) -> str:
        """access token이 없으면 갱신 후 반환한다."""
        if not self._access_token:
            await self.refresh_token()
        return self._access_token

    async def _get_sentinel_token(self, access_token: str) -> str:
        """대화 요청에 필요한 sentinel 챌린지 토큰을 획득한다."""
        resp = await self._client.post(
            _SENTINEL_URL,
            headers={**_HEADERS, "Authorization": f"Bearer {access_token}"},
            json={},
        )
        if resp.status_code != 200:
            raise ChatGPTAPIError(f"sentinel 토큰 획득 실패: HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()  # type: ignore[no-untyped-call]
        sentinel = data.get("token")
        if not sentinel:
            raise ChatGPTAPIError("sentinel 응답에 token 필드가 없습니다.")

        pow_data = data.get("proofofwork", {})
        if pow_data.get("required"):
            pow_token = _solve_pow(
                seed=str(pow_data["seed"]),
                difficulty=str(pow_data["difficulty"]),
            )
            # proof token을 별도 헤더로 저장해두기 위해 인스턴스에 캐시
            self._pow_token = pow_token

        return str(sentinel)

    async def stream_message(
        self,
        message: str,
        conversation_id: str | None = None,
        parent_message_id: str | None = None,
        model: str = "auto",
    ) -> AsyncGenerator[str]:
        """메시지를 전송하고 응답 텍스트를 스트리밍한다.

        Yields:
            응답 텍스트 조각 (delta)
        """
        token = await self._ensure_token()
        sentinel_token = await self._get_sentinel_token(token)

        body: dict[str, Any] = {
            "action": "next",
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": [message]},
                }
            ],
            "parent_message_id": parent_message_id or str(uuid.uuid4()),
            "model": model,
            "stream": True,
        }
        if conversation_id:
            body["conversation_id"] = conversation_id

        headers: dict[str, str] = {
            **_HEADERS,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "oai-device-id": self._device_id,
            "oai-language": "ko-KR",
            "openai-sentinel-chat-requirements-token": sentinel_token,
        }
        if self._pow_token:
            headers["openai-sentinel-proof-token"] = self._pow_token

        resp = await self._client.post(
            _CONVERSATION_URL,
            json=body,
            headers=headers,
            stream=True,
        )

        if resp.status_code == 401:
            await self.refresh_token()
            raise ChatGPTAuthError("토큰이 만료됐습니다. 다시 시도하세요.")
        if resp.status_code == 403:
            raise ChatGPTAPIError(f"접근 거부됨 (403): {resp.text[:300]}")
        if resp.status_code == 429:
            raise ChatGPTAPIError("Rate limit 초과 (429). 잠시 후 다시 시도하세요.")
        if resp.status_code != 200:
            raise ChatGPTAPIError(f"대화 엔드포인트 오류: HTTP {resp.status_code}")

        buffer = ""
        async for chunk in resp.aiter_content():  # type: ignore[no-untyped-call]
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    return
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg = event.get("message", {})
                content = msg.get("content", {})
                parts = content.get("parts", [])
                # delta: 전체 누적 텍스트를 매번 전송 — 마지막 파트만 추출
                if parts and isinstance(parts[0], str) and parts[0]:
                    yield parts[0]

    async def send_message(self, message: str, model: str = "auto") -> str:
        """메시지를 전송하고 전체 응답 텍스트를 반환한다."""
        last_text = ""
        async for text in self.stream_message(message, model=model):
            last_text = text  # backend-api는 누적 텍스트를 매 이벤트마다 전송
        return last_text

    async def health_check(self) -> dict[str, Any]:
        """OAuth 엔드포인트 상태를 확인한다.

        Returns:
            {"ok": bool, "error": str | None, "model": str | None}
        """
        try:
            token = await self.refresh_token()
            # 간단한 메시지로 실제 응답 확인
            response = await self.send_message("respond with exactly: OK", model="auto")
            return {
                "ok": True,
                "error": None,
                "token_preview": token[:20] + "...",
                "response_preview": response[:50],
            }
        except ChatGPTAuthError as e:
            return {"ok": False, "error": f"인증 오류: {e}", "token_preview": None, "response_preview": None}
        except ChatGPTAPIError as e:
            return {"ok": False, "error": f"API 오류: {e}", "token_preview": None, "response_preview": None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"알 수 없는 오류: {e}", "token_preview": None, "response_preview": None}


def get_client() -> ChatGPTOAuthClient:
    """환경변수에서 세션 토큰을 읽어 클라이언트를 반환한다."""
    return ChatGPTOAuthClient()
