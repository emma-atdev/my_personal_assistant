"""Chainlit 채팅 UI — 개인 비서 프론트엔드."""

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from agent.orchestrator import create_orchestrator


@cl.on_chat_start
async def on_chat_start() -> None:
    """새 채팅 세션 시작 시 에이전트를 초기화한다."""
    session_id = cl.user_session.get("id") or "default"
    agent, config = create_orchestrator(thread_id=str(session_id))

    cl.user_session.set("agent", agent)
    cl.user_session.set("config", config)

    await cl.Message(
        content=(
            "안녕하세요! AI 개발자 전용 개인 비서입니다.\n\n"
            "**가능한 것들:**\n"
            "- 웹 검색 및 최신 정보 조회\n"
            "- ArXiv · HuggingFace 논문 탐색\n"
            "- 메모 저장 및 검색\n"
            "- 로컬 파일 분석 (MCP 연결 시)\n"
            "- API 비용 확인\n\n"
            "무엇을 도와드릴까요?"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """사용자 메시지를 받아 에이전트 응답을 스트리밍한다."""
    agent: CompiledStateGraph = cl.user_session.get("agent")  # type: ignore[assignment]
    config: RunnableConfig = cl.user_session.get("config")  # type: ignore[assignment]

    msg = cl.Message(content="")
    await msg.send()

    # 스트리밍 응답 (Responses API content block 형식도 처리)
    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=message.content or "")]},
        config,
        version="v2",
    ):
        if event["event"] != "on_chat_model_stream":
            continue
        chunk = event["data"].get("chunk")
        if not chunk or not hasattr(chunk, "content"):
            continue
        content = chunk.content
        if isinstance(content, str) and content:
            await msg.stream_token(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        await msg.stream_token(text)

    await msg.update()

    # HITL 인터럽트 확인
    state = agent.get_state(config)
    if state.next:
        await _handle_hitl(agent, config, state)


async def _handle_hitl(
    agent: CompiledStateGraph,  # type: ignore[type-arg]
    config: RunnableConfig,
    state: object,
) -> None:
    """HITL 인터럽트 처리 — 실행 예정 툴을 보여주고 사용자 확인을 받는다."""
    pending_tools = [t.name for t in getattr(state, "tasks", [])]
    tool_info = ", ".join(pending_tools) if pending_tools else "알 수 없는 작업"

    res = await cl.AskActionMessage(
        content=f"**확인이 필요합니다**\n실행 예정: `{tool_info}`\n진행할까요?",
        actions=[
            cl.Action(name="confirm", payload={"value": "y"}, label="확인"),
            cl.Action(name="cancel", payload={"value": "n"}, label="취소"),
        ],
    ).send()

    confirmed = res and res.get("name") == "confirm"

    if confirmed:
        result = await agent.ainvoke(None, config)
        response = _extract_text(result.get("messages", []))
        await cl.Message(content=response or "완료됐습니다.").send()
    else:
        await cl.Message(content="작업이 취소됐습니다.").send()


def _extract_text(messages: list[object]) -> str:
    """메시지 목록에서 마지막 AI 응답 텍스트를 추출한다."""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            content = m.content
            if isinstance(content, list):
                return " ".join(
                    block["text"] for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            return str(content)
    return ""
