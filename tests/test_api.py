"""backend/app.py FastAPI 엔드포인트 테스트."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_costs_empty() -> None:
    response = client.get("/api/costs")
    assert response.status_code == 200
    assert "summary" in response.json()


# ── /api/chat ─────────────────────────────────────────────────


def _make_mock_orchestrator(
    events: list[dict[str, Any]], *, has_interrupt: bool = False
) -> tuple[MagicMock, MagicMock]:
    """create_orchestrator 반환값을 모킹한다."""

    async def _mock_stream_events(*_args: object, **_kwargs: object) -> Any:
        for ev in events:
            yield ev

    mock_state = MagicMock()
    mock_state.next = ["__interrupt__"] if has_interrupt else []
    mock_state.values = {
        "messages": [
            MagicMock(
                tool_calls=[{"name": "create_event", "args": {"summary": "테스트"}, "id": "call_123"}],
                content="",
            )
        ]
        if has_interrupt
        else []
    }

    mock_agent = MagicMock()
    mock_agent.astream_events = _mock_stream_events
    mock_agent.aget_state = AsyncMock(return_value=mock_state)

    mock_config: MagicMock = MagicMock()
    return mock_agent, mock_config


def test_chat_stream_returns_sse() -> None:
    """정상 대화 흐름 — SSE 스트림에 token·done 포함 확인."""
    import json

    events = [
        {
            "event": "on_chat_model_stream",
            "metadata": {"checkpoint_ns": ""},
            "data": {"chunk": MagicMock(content="안녕하세요")},
        },
    ]
    mock_agent, mock_config = _make_mock_orchestrator(events)

    with patch("backend.app.create_orchestrator", return_value=(mock_agent, mock_config)):
        response = client.post("/api/chat", json={"thread_id": "test-1", "message": "안녕"})

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    lines = [line for line in response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line[6:]) for line in lines]
    types = [p["type"] for p in payloads]

    assert "token" in types
    assert "done" in types


def test_chat_stream_hitl_event() -> None:
    """HITL 중단 — hitl 이벤트가 SSE에 포함되는지 확인."""
    import json

    mock_agent, mock_config = _make_mock_orchestrator([], has_interrupt=True)

    with patch("backend.app.create_orchestrator", return_value=(mock_agent, mock_config)):
        response = client.post("/api/chat", json={"thread_id": "test-hitl", "message": "일정 추가해줘"})

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line[6:]) for line in lines]
    types = [p["type"] for p in payloads]

    assert "hitl" in types
    hitl = next(p for p in payloads if p["type"] == "hitl")
    assert hitl["tool_name"] == "create_event"
    assert hitl["tool_call_id"] == "call_123"


# ── /api/chat/resume ─────────────────────────────────────────


def test_chat_resume_cancel() -> None:
    """취소 흐름 — ToolMessage 주입 후 에이전트 재개."""
    from langchain_core.messages import AIMessage

    mock_agent = MagicMock()
    mock_agent.aupdate_state = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="작업이 취소됐습니다.")]})

    with patch("backend.app.create_orchestrator", return_value=(mock_agent, MagicMock())):
        response = client.post(
            "/api/chat/resume",
            json={
                "thread_id": "test-2",
                "confirmed": False,
                "tool_name": "create_event",
                "tool_args": {},
                "tool_call_id": "call_abc",
            },
        )

    assert response.status_code == 200
    assert "response" in response.json()
    mock_agent.aupdate_state.assert_called_once()


def test_chat_resume_confirm_direct_tool() -> None:
    """확인 흐름 (직접 실행 툴) — _execute_hitl_tool 호출 후 재개."""
    from langchain_core.messages import AIMessage

    mock_agent = MagicMock()
    mock_agent.aupdate_state = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="일정이 생성됐습니다.")]})

    with (
        patch("backend.app.create_orchestrator", return_value=(mock_agent, MagicMock())),
        patch("backend.app._execute_hitl_tool", return_value="일정 생성 완료") as mock_exec,
    ):
        response = client.post(
            "/api/chat/resume",
            json={
                "thread_id": "test-3",
                "confirmed": True,
                "tool_name": "create_event",
                "tool_args": {"summary": "팀 미팅"},
                "tool_call_id": "call_def",
            },
        )

    assert response.status_code == 200
    assert response.json()["response"] == "일정이 생성됐습니다."
    mock_exec.assert_called_once_with("create_event", {"summary": "팀 미팅"})


# ── /api/chat/messages/{thread_id} ───────────────────────────


@pytest.mark.asyncio
async def test_get_messages_empty() -> None:
    """빈 thread — 메시지 없이 200 반환."""
    mock_agent = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {"messages": []}
    mock_agent.aget_state = AsyncMock(return_value=mock_state)

    with (
        patch("backend.app.create_orchestrator", return_value=(mock_agent, MagicMock())),
        patch("backend.app.load_message_metadata", return_value={}, create=True),
    ):
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            response = await ac.get("/api/chat/messages/empty-thread")

    assert response.status_code == 200
    assert response.json() == {"messages": []}
