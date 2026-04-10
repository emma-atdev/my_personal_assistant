"""서브에이전트 공통 유틸리티."""

from typing import Any


def get_subagent_model(
    claude_model: str = "claude-haiku-4-5",
    pkce_model: str = "gpt-5.1-codex-mini",
    openai_fallback: str = "openai:gpt-4o-mini",
) -> Any:
    """서브에이전트용 모델 — Claude OAuth → ChatGPT PKCE → OpenAI API 폴백."""
    try:
        from auth.langchain_claude import check_tokens_available
        from auth.langchain_claude import get_model as get_claude_model

        if check_tokens_available():
            return get_claude_model(oauth_model=claude_model)
    except Exception:  # noqa: BLE001
        pass

    from auth.langchain_chatgpt import get_model

    return get_model(pkce_model=pkce_model, openai_fallback=openai_fallback)
