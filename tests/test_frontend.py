"""frontend/app.py 단위 테스트 — Streamlit 세션 없이 순수 로직만 검증."""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch


# ── _export_chat ─────────────────────────────────────────────


def _make_messages(*msgs: dict[str, Any]) -> list[dict[str, Any]]:
    return list(msgs)


def _call_export(messages: list[dict[str, Any]]) -> str:
    """st.session_state를 mocking해 _export_chat을 호출한다."""
    mock_state = MagicMock()
    mock_state.messages = messages

    with patch("frontend.app.st") as mock_st:
        mock_st.session_state = mock_state
        from frontend.app import _export_chat

        return _export_chat()


def test_export_basic() -> None:
    """user/assistant 메시지가 Markdown으로 변환된다."""
    messages = _make_messages(
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요!", "elapsed": 0, "steps": []},
    )
    result = _call_export(messages)
    assert "사용자" in result
    assert "비서" in result
    assert "안녕" in result
    assert "안녕하세요!" in result


def test_export_elapsed_steps() -> None:
    """elapsed와 steps가 export에 포함된다."""
    messages = _make_messages(
        {"role": "user", "content": "질문"},
        {
            "role": "assistant",
            "content": "답변",
            "elapsed": 5,
            "steps": [{"label": "웹 검색 중", "elapsed": 3}],
        },
    )
    result = _call_export(messages)
    assert "5초" in result
    assert "웹 검색 중" in result


def test_export_missing_content_key() -> None:
    """`content` 키가 없는 메시지에서 KeyError가 나지 않는다."""
    messages = _make_messages(
        {"role": "user"},  # content 누락
        {"role": "assistant", "elapsed": 0, "steps": []},  # content 누락
    )
    result = _call_export(messages)  # 예외 없이 실행되어야 함
    assert isinstance(result, str)


def test_export_no_elapsed_zero() -> None:
    """elapsed=0이면 시간 표시가 생략된다."""
    messages = _make_messages(
        {"role": "assistant", "content": "답변", "elapsed": 0, "steps": []},
    )
    result = _call_export(messages)
    assert "초" not in result


def test_export_empty_steps() -> None:
    """steps가 비어있으면 단계 표시가 생략된다."""
    messages = _make_messages(
        {"role": "assistant", "content": "답변", "elapsed": 3, "steps": []},
    )
    result = _call_export(messages)
    assert "단계" not in result


def test_export_includes_timestamp() -> None:
    """export 결과 상단에 날짜가 포함된다."""
    messages: list[dict[str, Any]] = []
    today = datetime.now().strftime("%Y-%m-%d")
    result = _call_export(messages)
    assert today in result


# ── MCP config ───────────────────────────────────────────────


def test_allowed_dirs_str_reads_config() -> None:
    """config.yaml의 허용 경로를 읽어 문자열로 반환한다."""
    from utils.mcp_config import allowed_dirs_str

    result = allowed_dirs_str()
    assert "my_personal_assistant" in result


def test_allowed_dirs_str_fallback(tmp_path: Any, monkeypatch: Any) -> None:
    """config.yaml이 없으면 기본값을 반환한다."""
    import utils.mcp_config as mcp_cfg

    monkeypatch.setattr(mcp_cfg, "_CONFIG_PATH", tmp_path / "nonexistent.yaml")
    result = mcp_cfg.allowed_dirs_str()
    assert result == "~/my_personal_assistant"


# ── MCP _is_allowed deny 패턴 ────────────────────────────────


def test_is_allowed_blocks_env() -> None:
    """.env 파일은 deny 패턴으로 차단된다."""
    from mcp_server.main import _is_allowed

    assert _is_allowed("~/my_personal_assistant/.env") is False


def test_is_allowed_blocks_env_variants() -> None:
    """.env.local, .env.prod 등도 차단된다."""
    from mcp_server.main import _is_allowed

    assert _is_allowed("~/my_personal_assistant/.env.local") is False
    assert _is_allowed("~/my_personal_assistant/.env.prod") is False


def test_is_allowed_permits_source_files() -> None:
    """소스 코드 파일은 허용된다."""
    from mcp_server.main import _is_allowed

    assert _is_allowed("~/my_personal_assistant/agent/orchestrator.py") is True
    assert _is_allowed("~/my_personal_assistant/README.md") is True


def test_is_allowed_blocks_outside_dir() -> None:
    """허용 경로 외부는 차단된다."""
    from mcp_server.main import _is_allowed

    assert _is_allowed("/etc/passwd") is False
    assert _is_allowed("~/Downloads/file.txt") is False


# ── MCP list_local_files ignore 필터 ─────────────────────────


def test_list_local_files_excludes_venv() -> None:
    """.venv 디렉토리가 목록에 포함되지 않는다."""
    from mcp_server.main import list_local_files

    result = list_local_files("~/my_personal_assistant")
    assert ".venv" not in result


def test_list_local_files_excludes_git() -> None:
    """.git 디렉토리가 목록에 포함되지 않는다."""
    from mcp_server.main import list_local_files

    result = list_local_files("~/my_personal_assistant")
    assert ".git/" not in result and "/.git" not in result


def test_list_local_files_includes_source() -> None:
    """소스 코드 파일은 목록에 포함된다."""
    from mcp_server.main import list_local_files

    result = list_local_files("~/my_personal_assistant")
    assert "agent/orchestrator.py" in result
