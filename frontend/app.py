"""Streamlit 채팅 UI — 개인 비서 프론트엔드."""

import asyncio
import queue
import threading
import uuid
from collections.abc import Generator

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from agent.orchestrator import create_orchestrator

st.set_page_config(page_title="개인 비서", layout="wide")


def _init_session() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "agent" not in st.session_state:
        agent, config = create_orchestrator(thread_id=st.session_state.session_id)
        st.session_state.agent = agent
        st.session_state.config = config
    if "messages" not in st.session_state:
        st.session_state.messages = []


async def _stream_tokens(agent: object, config: object, user_input: str) -> None:
    """에이전트 스트리밍 이벤트를 큐에 전달한다."""
    async for event in agent.astream_events(  # type: ignore[union-attr]
        {"messages": [HumanMessage(content=user_input)]},
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
            yield content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        yield text


def _run_stream(user_input: str) -> Generator[str]:
    """async 스트리밍을 별도 스레드에서 실행해 sync generator로 변환한다."""
    agent = st.session_state.agent
    config = st.session_state.config
    token_queue: queue.Queue[str | None] = queue.Queue()

    async def _producer() -> None:
        async for token in _stream_tokens(agent, config, user_input):
            token_queue.put(token)
        token_queue.put(None)

    def _thread_target() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_producer())
        finally:
            loop.close()

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()

    while True:
        token = token_queue.get()
        if token is None:
            break
        yield token

    thread.join()


@st.dialog("확인이 필요합니다")
def _hitl_dialog(tool_info: str) -> None:
    st.warning(f"실행 예정: `{tool_info}`")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("확인", use_container_width=True):
            st.session_state.hitl_confirmed = True
            st.rerun()
    with col2:
        if st.button("취소", use_container_width=True):
            st.session_state.hitl_confirmed = False
            st.rerun()


def _handle_hitl() -> None:
    state = st.session_state.agent.get_state(st.session_state.config)
    if not state.next:
        return

    pending_tools = [t.name for t in getattr(state, "tasks", [])]
    tool_info = ", ".join(pending_tools) if pending_tools else "알 수 없는 작업"

    if "hitl_confirmed" not in st.session_state:
        _hitl_dialog(tool_info)
        return

    confirmed = st.session_state.pop("hitl_confirmed")

    def _run_async(coro):  # type: ignore[no-untyped-def]
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    if confirmed:
        result = _run_async(st.session_state.agent.ainvoke(None, st.session_state.config))
        response = _extract_text(result.get("messages", []))
        st.session_state.messages.append({"role": "assistant", "content": response or "완료됐습니다."})
    else:
        st.session_state.messages.append({"role": "assistant", "content": "작업이 취소됐습니다."})


def _extract_text(messages: list[object]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            content = m.content
            if isinstance(content, list):
                return " ".join(
                    block["text"] for block in content if isinstance(block, dict) and block.get("type") == "text"
                )
            return str(content)
    return ""


def main() -> None:
    _init_session()

    with st.sidebar:
        st.title("개인 비서")
        st.markdown(
            "**가능한 것들:**\n"
            "- 웹 검색 및 최신 정보 조회\n"
            "- ArXiv · HuggingFace 논문 탐색\n"
            "- 메모 저장 및 검색\n"
            "- 로컬 파일 분석 (MCP 연결 시)\n"
            "- API 비용 확인"
        )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("메시지를 입력하세요..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            response = st.write_stream(_run_stream(user_input))

        st.session_state.messages.append({"role": "assistant", "content": response})
        _handle_hitl()


main()
