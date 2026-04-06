"""Claude.ai PKCE OAuth 클라이언트.

not-claude-code-emulator와 동일한 방식으로 Claude.ai 구독을 활용한다.
- 최초 1회 브라우저 로그인 → 토큰 저장
- 이후 자동 토큰 갱신

사용 방법:
    uv run python -m auth.claude_pkce login   # 최초 1회 로그인
    uv run python -m auth.claude_pkce test    # 메시지 전송 테스트
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_AUTH_URL = "https://claude.com/cai/oauth/authorize"
_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
_REDIRECT_URI = "http://localhost:3000/callback"
_SCOPES = "user:inference user:profile user:sessions:claude_code"
_CALLBACK_PORT = 3000
# not-claude-code-emulator가 저장하는 경로 (기본값)
_TOKEN_FILE = Path.home() / ".config" / "anthropic" / "q" / "tokens.json"
# 위 파일이 없을 때 폴백 경로
_TOKEN_FILE_FALLBACK = Path(__file__).parent.parent / ".claude_tokens.json"

# 만료 60초 전부터 갱신 (expiresAt은 밀리초)
_EXPIRY_BUFFER_MS = 60_000


class ClaudePKCEError(Exception):
    """Claude PKCE OAuth 오류."""


# ── PKCE 유틸 ──────────────────────────────────────────────


def _generate_pkce() -> tuple[str, str]:
    """code_verifier와 code_challenge(S256)를 생성한다."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _is_token_expired(tokens: dict[str, Any]) -> bool:
    """토큰이 만료됐는지 확인한다 (만료 60초 전부터 갱신).

    not-claude-code-emulator 형식(expiresAt, 밀리초)과
    자체 저장 형식(expires_at, 초) 모두 지원한다.
    """
    now_ms = int(time.time() * 1000)
    # camelCase (not-claude-code-emulator 형식)
    expires_at_ms = int(tokens.get("expiresAt", 0))
    if expires_at_ms:
        return now_ms >= expires_at_ms - _EXPIRY_BUFFER_MS
    # snake_case (자체 저장 형식, 초 단위)
    expires_at_s = int(tokens.get("expires_at", 0))
    if expires_at_s:
        return now_ms >= (expires_at_s * 1000) - _EXPIRY_BUFFER_MS
    return False


def _get_access_token(tokens: dict[str, Any]) -> str:
    """camelCase/snake_case 모두 지원하는 access_token 추출."""
    return str(tokens.get("accessToken") or tokens.get("access_token") or "")


def _get_refresh_token(tokens: dict[str, Any]) -> str:
    """camelCase/snake_case 모두 지원하는 refresh_token 추출."""
    return str(tokens.get("refreshToken") or tokens.get("refresh_token") or "")


# ── 토큰 저장/로드 ─────────────────────────────────────────


def save_tokens(tokens: dict[str, Any]) -> None:
    """토큰을 파일에 저장한다 (폴백 경로에 저장)."""
    _TOKEN_FILE_FALLBACK.write_text(json.dumps(tokens, indent=2))


def load_tokens() -> dict[str, Any] | None:
    """저장된 토큰을 로드한다. not-claude-code-emulator 경로를 우선 확인한다."""
    for path in (_TOKEN_FILE, _TOKEN_FILE_FALLBACK):
        if path.exists():
            try:
                return json.loads(path.read_text())  # type: ignore[no-any-return]
            except Exception:  # noqa: BLE001
                continue
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
                self.wfile.write(b"<html><body><h2>Claude login complete. You may close this tab.</h2></body></html>")
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass  # suppress access logs

    server = HTTPServer(("localhost", _CALLBACK_PORT), _Handler)
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
    }
    auth_url = f"{_AUTH_URL}?{urlencode(params)}"

    server, code_future = _start_callback_server()
    print(f"브라우저에서 로그인 중...\n{auth_url}")
    webbrowser.open(auth_url)

    try:
        code = await asyncio.wait_for(code_future, timeout=120)
    except TimeoutError as e:
        raise ClaudePKCEError("로그인 타임아웃 (120초)") from e
    finally:
        server.server_close()

    tokens = await _exchange_code(code, verifier)
    save_tokens(tokens)
    print("Claude 로그인 완료!")
    return tokens


async def _exchange_code(code: str, verifier: str) -> dict[str, Any]:
    """authorization code를 access/refresh token으로 교환한다."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
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
            raise ClaudePKCEError(f"토큰 교환 실패: HTTP {resp.status_code} — {resp.text[:200]}")
        data: dict[str, Any] = resp.json()

    return _parse_token_response(data)


def _parse_token_response(data: dict[str, Any]) -> dict[str, Any]:
    """토큰 응답을 정규화한다."""
    expires_in = data.get("expires_in", 3600)
    return {
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": int(time.time()) + expires_in,
        "expires_in": expires_in,
        "token_type": data.get("token_type", "Bearer"),
    }


async def refresh_tokens(tokens: dict[str, Any]) -> dict[str, Any]:
    """refresh_token으로 새 access_token을 획득하고 저장한다."""
    refresh_token = _get_refresh_token(tokens)
    if not refresh_token:
        raise ClaudePKCEError("refresh_token이 없습니다. 다시 로그인하세요: uv run python -m auth.claude_pkce login")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": _CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise ClaudePKCEError(f"토큰 갱신 실패: HTTP {resp.status_code} — {resp.text[:200]}")
        data: dict[str, Any] = resp.json()

    new_tokens = _parse_token_response(data)
    # refresh_token이 새로 발급되지 않으면 기존 것 유지
    if not new_tokens["refresh_token"]:
        new_tokens["refresh_token"] = refresh_token
    save_tokens(new_tokens)
    return new_tokens


async def get_valid_access_token() -> str:
    """유효한 access_token을 반환한다. 만료됐으면 자동 갱신한다."""
    tokens = load_tokens()
    if not tokens or not _get_access_token(tokens):
        raise ClaudePKCEError("토큰이 없습니다. 먼저 npx not-claude-code-emulator@latest install 로 로그인하세요.")
    if _is_token_expired(tokens):
        tokens = await refresh_tokens(tokens)
    return _get_access_token(tokens)


# ── CLI ───────────────────────────────────────────────────


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "login":
        asyncio.run(login())
    elif cmd == "test":

        async def _test() -> None:
            token = await get_valid_access_token()
            print(f"토큰 앞 20자: {token[:20]}...")

        asyncio.run(_test())
    else:
        print("Usage: uv run python -m auth.claude_pkce [login|test]")
