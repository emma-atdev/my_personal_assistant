"""Claude.ai OAuth 기반 LangChain 모델 팩토리.

not-claude-code-emulator (localhost:3000)를 프록시로 사용해
claude.ai 구독 계정으로 Claude 모델을 호출한다.
OAuth 토큰 관리, cch 서명, Claude Code 스푸핑 등을 에뮬레이터가 모두 처리한다.

사전 준비:
    npx not-claude-code-emulator@latest install  # 최초 1회
    npx not-claude-code-emulator@latest start    # MPA 실행 전 또는 자동 시작

폴백: ~/.config/anthropic/q/tokens.json 없으면 ANTHROPIC_API_KEY 사용
"""

from __future__ import annotations

from typing import Any

# 에뮬레이터 프록시 주소
_PROXY_BASE_URL = "http://localhost:3000"
# 더미 API 키 (에뮬레이터가 OAuth 토큰으로 교체함)
_DUMMY_API_KEY = "sk-ant-placeholder00"

_CLAUDE_TOKENS_AVAILABLE: bool | None = None  # 프로세스 내 캐시


def check_tokens_available() -> bool:
    """Claude OAuth 토큰 존재 여부를 확인한다."""
    global _CLAUDE_TOKENS_AVAILABLE
    if _CLAUDE_TOKENS_AVAILABLE is None:
        try:
            from auth.claude_pkce import _get_access_token, load_tokens

            tokens = load_tokens()
            _CLAUDE_TOKENS_AVAILABLE = bool(tokens and _get_access_token(tokens))
        except Exception:  # noqa: BLE001
            _CLAUDE_TOKENS_AVAILABLE = False
    return _CLAUDE_TOKENS_AVAILABLE is True


def _is_proxy_running() -> bool:
    """에뮬레이터 프록시가 localhost:3000에서 실행 중인지 확인한다 (IPv4/IPv6 모두 시도)."""
    import socket

    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((addr, 3000)) == 0:
                return True
    return False


def get_model(
    oauth_model: str = "claude-sonnet-4-6",
    anthropic_fallback: str = "anthropic:claude-sonnet-4-6",
) -> Any:
    """Claude OAuth 토큰이 있고 에뮬레이터가 실행 중이면 프록시 모델, 없으면 ANTHROPIC_API_KEY 기반 모델을 반환한다.

    Args:
        oauth_model: OAuth 사용 시 모델 ID (claude-sonnet-4-6, claude-opus-4-6 등)
        anthropic_fallback: 토큰/프록시 없을 때 langchain init_chat_model 문자열
    """
    if check_tokens_available() and _is_proxy_running():
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name=oauth_model,
            api_key=_DUMMY_API_KEY,  # type: ignore[arg-type]
            base_url=_PROXY_BASE_URL,
            timeout=None,
            stop=None,
        )

    from langchain.chat_models import init_chat_model

    return init_chat_model(anthropic_fallback)
