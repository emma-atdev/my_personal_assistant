"""ChatGPT PKCE OAuth 클라이언트.

openclaw와 동일한 방식으로 ChatGPT Plus 구독을 활용한다.
- 최초 1회 브라우저 로그인 → 토큰 저장
- 이후 자동 토큰 갱신

사용 방법:
    uv run python -m auth.chatgpt_pkce login   # 최초 1회 로그인
    uv run python -m auth.chatgpt_pkce test    # 메시지 전송 테스트
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from curl_cffi.requests import AsyncSession

_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_AUTH_URL = "https://auth.openai.com/oauth/authorize"
_TOKEN_URL = "https://auth.openai.com/oauth/token"
_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
_REDIRECT_URI = "http://127.0.0.1:1455/auth/callback"
_SCOPES = "openid profile email offline_access"
_CALLBACK_PORT = 1455
_TOKEN_FILE = Path(__file__).parent.parent / ".chatgpt_tokens.json"

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


class ChatGPTPKCEError(Exception):
    """PKCE OAuth 오류."""


# ── PKCE 유틸 ──────────────────────────────────────────────


def _generate_pkce() -> tuple[str, str]:
    """code_verifier와 code_challenge(S256)를 생성한다."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """JWT payload를 검증 없이 디코딩한다."""
    parts = token.split(".")
    if len(parts) < 2:  # noqa: PLR2004
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return dict(json.loads(base64.urlsafe_b64decode(payload)))
    except Exception:  # noqa: BLE001
        return {}


def _extract_account_id(access_token: str) -> str:
    """JWT에서 chatgpt_account_id를 추출한다."""
    payload = _decode_jwt_payload(access_token)
    return str(payload.get("https://api.openai.com/auth.chatgpt_account_id", ""))


def _is_token_expired(access_token: str) -> bool:
    """JWT access_token이 만료됐는지 확인한다 (만료 60초 전부터 갱신)."""
    import time

    payload = _decode_jwt_payload(access_token)
    exp = int(payload.get("exp", 0))
    return exp > 0 and int(time.time()) >= exp - 60


# ── 토큰 저장/로드 ─────────────────────────────────────────


def save_tokens(tokens: dict[str, Any]) -> None:
    """토큰을 파일에 저장한다."""
    _TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def load_tokens() -> dict[str, Any] | None:
    """저장된 토큰을 로드한다. 없으면 None."""
    if not _TOKEN_FILE.exists():
        return None
    try:
        return json.loads(_TOKEN_FILE.read_text())  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001
        return None


# ── 콜백 서버 ─────────────────────────────────────────────


def _start_callback_server() -> tuple[HTTPServer, asyncio.Future[str]]:
    """로컬 콜백 서버를 시작하고 authorization code를 받는 Future를 반환한다."""
    loop = asyncio.get_event_loop()
    future: asyncio.Future[str] = loop.create_future()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            codes = params.get("code", [])
            if codes:
                code = codes[0]
                loop.call_soon_threadsafe(future.set_result, code)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Login complete. You may close this tab.</h2></body></html>")
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass  # suppress access logs

    server = HTTPServer(("127.0.0.1", _CALLBACK_PORT), _Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server, future


# ── OAuth 흐름 ─────────────────────────────────────────────


async def login() -> dict[str, Any]:
    """PKCE OAuth 로그인을 수행하고 토큰을 반환한다.

    브라우저가 자동으로 열립니다. 로그인 후 자동으로 토큰이 저장됩니다.
    """
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "scope": _SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "opencode",
    }
    auth_url = f"{_AUTH_URL}?{urlencode(params)}"

    server, code_future = _start_callback_server()
    print(f"브라우저에서 로그인 중...\n{auth_url}")
    webbrowser.open(auth_url)

    try:
        code = await asyncio.wait_for(code_future, timeout=120)
    except TimeoutError as e:
        raise ChatGPTPKCEError("로그인 타임아웃 (120초)") from e
    finally:
        server.server_close()

    tokens = await _exchange_code(code, verifier)
    save_tokens(tokens)
    print(f"로그인 완료! account_id: {tokens.get('account_id', 'unknown')}")
    return tokens


async def _exchange_code(code: str, verifier: str) -> dict[str, Any]:
    """authorization code를 access/refresh token으로 교환한다."""
    async with AsyncSession(impersonate="chrome124") as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": _CLIENT_ID,
                "redirect_uri": _REDIRECT_URI,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise ChatGPTPKCEError(f"토큰 교환 실패: HTTP {resp.status_code} — {resp.text[:200]}")
        data: dict[str, Any] = resp.json()  # type: ignore[no-untyped-call, unused-ignore]

    access_token = data.get("access_token", "")
    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token", ""),
        "expires_in": data.get("expires_in", 3600),
        "account_id": _extract_account_id(access_token),
    }


async def refresh_tokens(tokens: dict[str, Any]) -> dict[str, Any]:
    """refresh_token으로 새 access_token을 획득하고 저장한다."""
    async with AsyncSession(impersonate="chrome124") as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": _CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise ChatGPTPKCEError(f"토큰 갱신 실패: HTTP {resp.status_code} — {resp.text[:200]}")
        data: dict[str, Any] = resp.json()  # type: ignore[no-untyped-call, unused-ignore]

    access_token = data.get("access_token", "")
    new_tokens = {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token", tokens["refresh_token"]),
        "expires_in": data.get("expires_in", 3600),
        "account_id": _extract_account_id(access_token) or tokens.get("account_id", ""),
    }
    save_tokens(new_tokens)
    return new_tokens


# ── Codex 클라이언트 ───────────────────────────────────────


class ChatGPTCodexClient:
    """ChatGPT Codex API 클라이언트 (PKCE OAuth 기반)."""

    def __init__(self, tokens: dict[str, Any] | None = None) -> None:
        self._tokens = tokens or load_tokens() or {}
        self._session = AsyncSession(impersonate="chrome124", headers=_HEADERS)

    async def __aenter__(self) -> ChatGPTCodexClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._session.close()  # type: ignore[no-untyped-call, unused-ignore]

    async def _ensure_tokens(self) -> dict[str, Any]:
        """토큰이 없으면 에러, 만료됐으면 갱신 후 반환."""
        if not self._tokens.get("access_token"):
            raise ChatGPTPKCEError("토큰이 없습니다. 먼저 로그인하세요: uv run python -m auth.chatgpt_pkce login")
        if _is_token_expired(self._tokens["access_token"]):
            self._tokens = await refresh_tokens(self._tokens)
        return self._tokens

    async def send_message(self, message: str, model: str = "gpt-5.1-codex-mini") -> str:
        """메시지를 전송하고 전체 응답을 반환한다."""
        last_text = ""
        async for chunk in self.stream_message(message, model=model):
            last_text = chunk
        return last_text

    async def stream_message(
        self,
        message: str,
        model: str = "gpt-5.1-codex-mini",
    ) -> Any:
        """메시지를 전송하고 응답 텍스트를 스트리밍한다."""
        tokens = await self._ensure_tokens()
        access_token = tokens["access_token"]
        account_id = tokens.get("account_id", "")

        headers = {
            **_HEADERS,
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "pi",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": message}],
            "stream": True,
            "store": False,
            "instructions": "You are a helpful assistant.",
            "text": {"verbosity": "medium"},
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }

        resp = await self._session.post(
            _CODEX_URL,
            json=body,
            headers=headers,
            stream=True,
        )

        if resp.status_code == 401:
            # 토큰 만료 → 갱신 후 재시도
            self._tokens = await refresh_tokens(self._tokens)
            async for chunk in self.stream_message(message, model=model):
                yield chunk
            return

        if resp.status_code != 200:
            body_text = resp.text
            raise ChatGPTPKCEError(f"codex 엔드포인트 오류: HTTP {resp.status_code} — {body_text[:300]}")

        buffer = ""
        current_text = ""
        async for chunk in resp.aiter_content():  # type: ignore[no-untyped-call, unused-ignore]
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw in ("[DONE]", ""):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Responses API SSE 포맷 파싱
                event_type = event.get("type", "")
                if event_type == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        current_text += delta
                        yield current_text
                elif event_type == "response.done":
                    break

    async def stream_responses(
        self,
        inputs: list[dict[str, Any]],
        system: str = "You are a helpful assistant.",
        tools: list[dict[str, Any]] | None = None,
        model: str = "gpt-5.1-codex-mini",
    ) -> Any:
        """Responses API 형식으로 전체 대화(멀티턴 + 툴콜)를 스트리밍한다.

        Args:
            inputs: Responses API 입력 메시지 목록
            system: 시스템 프롬프트 (instructions)
            tools: 툴 정의 목록
            model: 사용할 모델 ID

        Yields:
            Responses API SSE 이벤트 dict
        """
        tokens = await self._ensure_tokens()
        access_token = tokens["access_token"]
        account_id = tokens.get("account_id", "")

        headers = {
            **_HEADERS,
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "pi",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "model": model,
            "input": inputs,
            "stream": True,
            "store": False,
            "instructions": system,
            "text": {"verbosity": "medium"},
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        if tools:
            body["tools"] = tools

        resp = await self._session.post(
            _CODEX_URL,
            json=body,
            headers=headers,
            stream=True,
        )

        if resp.status_code == 401:
            self._tokens = await refresh_tokens(self._tokens)
            async for event in self.stream_responses(inputs, system, tools, model):
                yield event
            return

        if resp.status_code != 200:
            raise ChatGPTPKCEError(f"codex 엔드포인트 오류: HTTP {resp.status_code} — {resp.text[:300]}")

        buffer = ""
        async for chunk in resp.aiter_content():  # type: ignore[no-untyped-call, unused-ignore]
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw in ("[DONE]", ""):
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    continue

    async def health_check(self) -> dict[str, Any]:
        """연결 상태를 확인한다."""
        try:
            response = await self.send_message("respond with exactly: OK")
            return {"ok": True, "error": None, "response_preview": response[:50]}
        except ChatGPTPKCEError as e:
            return {"ok": False, "error": str(e), "response_preview": None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"알 수 없는 오류: {e}", "response_preview": None}


# ── CLI ───────────────────────────────────────────────────


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "login":
        asyncio.run(login())
    elif cmd == "test":

        async def _test() -> None:
            async with ChatGPTCodexClient() as client:
                result = await client.health_check()
                print(result)

        asyncio.run(_test())
    else:
        print("Usage: uv run python -m auth.chatgpt_pkce [login|test]")
