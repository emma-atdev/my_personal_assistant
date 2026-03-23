"""Streamlit 채팅 UI — 개인 비서 프론트엔드."""

import asyncio
import queue
import threading
from collections.abc import AsyncGenerator, Generator
from datetime import date, datetime
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()  # .env 로드 후 에이전트 임포트

from agent.orchestrator import create_orchestrator  # noqa: E402

st.set_page_config(page_title="개인 비서", page_icon="🤖", layout="wide")

# ── 상수 ─────────────────────────────────────────────────────

_QUICK_ACTIONS = [
    ("📅 오늘 일정", "오늘 일정 알려줘"),
    ("🗓️ 이번 주 일정", "이번 주 일정 알려줘"),
    ("🐙 내 이슈", "내 GitHub 이슈 목록 알려줘"),
    ("🔀 내 PR", "내 GitHub PR 목록 알려줘"),
    ("📄 논문 브리핑", "최신 AI 논문 브리핑해줘"),
    ("📝 Changelog", "changelog 보여줘"),
    ("💰 API 비용", "이번 달 API 비용 알려줘"),
]

_TOOL_LABELS: dict[str, str] = {
    "task": "🤖 서브에이전트 실행 중",
    "tavily_search_results_json": "🔍 웹 검색 중",
    "search_web": "🔍 웹 검색 중",
    "fetch_arxiv_papers": "📚 논문 검색 중",
    "fetch_hf_daily_papers": "📚 논문 검색 중",
    "fetch_pwc_trending": "📚 논문 트렌드 조회 중",
    "search_notes": "📝 메모 검색 중",
    "create_note": "📝 메모 저장 중",
    "list_notes": "📝 메모 목록 조회 중",
    "save_memory": "💾 기억 저장 중",
    "get_memory": "🧠 기억 조회 중",
    "list_memories": "🧠 기억 목록 조회 중",
    "delete_memory": "🧠 기억 삭제 중",
    "list_events": "📅 일정 조회 중",
    "create_event": "📅 일정 생성 중",
    "get_today_schedule": "📅 오늘 일정 조회 중",
    "get_cost_summary": "💰 비용 확인 중",
    "append_changelog": "📝 Changelog 기록 중",
    "read_changelog": "📝 Changelog 조회 중",
    "list_my_issues": "🐙 이슈 조회 중",
    "list_my_prs": "🔀 PR 조회 중",
    "get_issue": "🐙 이슈 상세 조회 중",
    "create_issue": "🐙 이슈 생성 중",
    "comment_on_issue": "💬 댓글 작성 중",
    "list_repo_issues": "🐙 레포 이슈 조회 중",
    "search_notion": "📓 Notion 검색 중",
    "get_notion_page": "📓 Notion 페이지 조회 중",
    "create_notion_page": "📓 Notion 페이지 생성 중",
    "append_notion_block": "📓 Notion 내용 추가 중",
    "sync_changelog_to_notion": "📓 Notion 동기화 중",
    "execute": "⚙️ 코드 실행 중",
    "write_file": "📁 파일 작성 중",
    "edit_file": "📁 파일 수정 중",
    "read_file": "📁 파일 읽는 중",
}


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, f"🔧 {name} 실행 중")


# ── 세션 초기화 ───────────────────────────────────────────────


def _init_session() -> None:
    if "agent" not in st.session_state:
        agent, config = create_orchestrator(thread_id="default")
        st.session_state.agent = agent
        st.session_state.config = config
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "quick_input" not in st.session_state:
        st.session_state.quick_input = ""
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = {"input": 0, "output": 0}
    if "briefing_read" not in st.session_state:
        st.session_state.briefing_read = False


# ── 이벤트 스트리밍 ───────────────────────────────────────────


async def _stream_events(agent: Any, config: Any, user_input: str) -> AsyncGenerator[dict[str, Any]]:
    """에이전트 이벤트를 스트리밍한다."""
    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=user_input)]},
        config,
        version="v2",
    ):
        etype = event["event"]

        if etype == "on_chat_model_stream":
            # 서브에이전트 출력 제외 — 서브에이전트는 checkpoint_ns가 'tools:'로 시작
            metadata = event.get("metadata", {})
            if metadata.get("checkpoint_ns", "").startswith("tools:"):
                continue
            chunk = event["data"].get("chunk")
            if not chunk or not hasattr(chunk, "content"):
                continue
            content = chunk.content
            if isinstance(content, str) and content:
                yield {"type": "token", "text": content}
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            yield {"type": "token", "text": text}

        elif etype == "on_tool_start":
            # 서브에이전트 내부 툴은 제외 — 오케스트레이터 레벨 툴만 표시
            if not event.get("metadata", {}).get("checkpoint_ns", "").startswith("tools:"):
                yield {"type": "tool_start", "name": event.get("name", "")}

        elif etype == "on_tool_end":
            if not event.get("metadata", {}).get("checkpoint_ns", "").startswith("tools:"):
                yield {"type": "tool_end", "name": event.get("name", "")}

        elif etype == "on_chat_model_end":
            output = event["data"].get("output")
            if output and hasattr(output, "usage_metadata") and output.usage_metadata:
                usage = output.usage_metadata
                # usage_metadata는 dict 또는 UsageMetadata 객체일 수 있음
                if isinstance(usage, dict):
                    input_t = usage.get("input_tokens", 0)
                    output_t = usage.get("output_tokens", 0)
                else:
                    input_t = getattr(usage, "input_tokens", 0)
                    output_t = getattr(usage, "output_tokens", 0)
                yield {"type": "usage", "input_tokens": input_t, "output_tokens": output_t}


def _run_events(user_input: str) -> Generator[dict[str, Any]]:
    """async 이벤트 스트리밍을 sync generator로 변환한다."""
    agent = st.session_state.agent
    config = st.session_state.config
    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    async def _producer() -> None:
        try:
            async for ev in _stream_events(agent, config, user_input):
                event_queue.put(ev)
        except Exception:  # noqa: BLE001
            pass
        finally:
            event_queue.put(None)

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
        ev = event_queue.get()
        if ev is None:
            break
        yield ev

    thread.join()


# ── HITL ─────────────────────────────────────────────────────


@st.dialog("확인이 필요합니다")
def _hitl_dialog(tool_name: str, tool_args: dict[str, Any]) -> None:
    st.warning(f"**{_tool_label(tool_name)}** 실행 전 확인이 필요합니다.")
    if tool_args:
        st.markdown("**실행 인수:**")
        st.json(tool_args)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 확인", use_container_width=True):
            st.session_state.hitl_confirmed = True
            st.rerun()
    with col2:
        if st.button("❌ 취소", use_container_width=True):
            st.session_state.hitl_confirmed = False
            st.rerun()


def _handle_hitl() -> None:
    state = st.session_state.agent.get_state(st.session_state.config)
    if not state.next:
        return

    # 마지막 AIMessage의 tool_calls에서 도구명·인수 추출
    messages = state.values.get("messages", [])
    tool_name = "알 수 없는 작업"
    tool_args: dict[str, Any] = {}
    if messages:
        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            if isinstance(tc, dict):
                tool_name = tc.get("name", tool_name)
                tool_args = tc.get("args", {})
            else:
                tool_name = getattr(tc, "name", tool_name)
                tool_args = getattr(tc, "args", {})

    if "hitl_confirmed" not in st.session_state:
        _hitl_dialog(tool_name, tool_args)
        return

    confirmed = st.session_state.pop("hitl_confirmed")

    def _run_async(coro: Any) -> Any:
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


# ── 사용자 입력 처리 ──────────────────────────────────────────


def _handle_user_input(user_input: str) -> None:
    """사용자 입력을 처리하고 응답을 스트리밍한다."""
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        status = st.status("생각 중...", expanded=False)
        text_box = st.empty()

        full_response = ""
        session_tokens = {"input": 0, "output": 0}

        for ev in _run_events(user_input):
            if ev["type"] == "token":
                full_response += ev["text"]
                text_box.markdown(full_response + "▌")
            elif ev["type"] == "tool_start":
                status.update(label=_tool_label(ev["name"]), state="running", expanded=False)
            elif ev["type"] == "tool_end":
                status.update(label="생각 중...", state="running", expanded=False)
            elif ev["type"] == "usage":
                session_tokens["input"] += ev["input_tokens"]
                session_tokens["output"] += ev["output_tokens"]

        status.update(label="완료", state="complete", expanded=False)
        text_box.markdown(full_response)

        # 이번 응답 토큰 표시
        total = session_tokens["input"] + session_tokens["output"]
        if total > 0:
            st.caption(f"↑ {session_tokens['input']:,} · ↓ {session_tokens['output']:,} 토큰")
            st.session_state.total_tokens["input"] += session_tokens["input"]
            st.session_state.total_tokens["output"] += session_tokens["output"]

    st.session_state.messages.append({"role": "assistant", "content": full_response})
    _handle_hitl()


# ── 내보내기 ──────────────────────────────────────────────────


def _export_chat() -> str:
    """대화 내역을 Markdown으로 변환한다."""
    lines = [f"# 대화 내역 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"]
    for msg in st.session_state.messages:
        role = "사용자" if msg["role"] == "user" else "비서"
        lines.append(f"**{role}:**\n\n{msg['content']}\n")
    return "\n---\n".join(lines)


# ── 메인 ─────────────────────────────────────────────────────


def main() -> None:
    _init_session()

    with st.sidebar:
        st.markdown("## 🤖 개인 비서")
        st.caption("LLM 전문 AI 개발자를 위한 비서")

        total_in = st.session_state.total_tokens["input"]
        total_out = st.session_state.total_tokens["output"]
        if total_in + total_out > 0:
            st.caption(f"세션 토큰  ↑ {total_in:,} · ↓ {total_out:,}")

        st.divider()

        # ── 브리핑 알림 ──────────────────────────────────────────
        if not st.session_state.briefing_read:
            from tools.notes import list_notes_raw

            today_str = date.today().strftime("%Y-%m-%d")
            recent = list_notes_raw(limit=10)
            today_briefing = next(
                (n for n in recent if "브리핑" in (n.get("tags") or "") and today_str in str(n.get("created_at", ""))),
                None,
            )
            if today_briefing:
                st.info(f"📬 오늘 브리핑이 도착했어요!\n\n**{today_briefing['title']}**")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📖 보기", use_container_width=True):
                        st.session_state.briefing_read = True
                        st.session_state.quick_input = "오늘 브리핑 보여줘"
                with col2:
                    if st.button("✕ 닫기", use_container_width=True):
                        st.session_state.briefing_read = True
                        st.rerun()
                st.divider()

        st.markdown("**⚡ 빠른 실행**")
        for label, query in _QUICK_ACTIONS:
            if st.button(label, use_container_width=True, key=f"quick_{label}"):
                st.session_state.quick_input = query

        st.divider()
        st.markdown(
            "**🛠️ 기능 목록**\n\n"
            "🔍 웹 검색 · 최신 정보 조회\n\n"
            "📚 ArXiv · HuggingFace 논문 탐색\n\n"
            "🐙 GitHub 이슈/PR 조회 · 생성 · 댓글\n\n"
            "📓 Notion 페이지 검색 · 조회 · 생성\n\n"
            "📅 Google Calendar 일정 조회 · 생성\n\n"
            "🐍 Python 코드 실행 (Modal 샌드박스)\n\n"
            "📁 로컬 파일 분석 (MCP 연결 시)\n\n"
            "💰 API 비용 확인\n\n"
            "📝 Changelog 자동 기록"
        )

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ 초기화", use_container_width=True):
                st.session_state.messages = []
                st.session_state.total_tokens = {"input": 0, "output": 0}
                st.rerun()
        with col2:
            if st.session_state.messages:
                st.download_button(
                    "⬇️ 내보내기",
                    data=_export_chat(),
                    file_name=f"chat_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    # ── 채팅 영역 ─────────────────────────────────────────────
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 빠른 실행 버튼 쿼리 처리
    if st.session_state.quick_input:
        user_input = st.session_state.quick_input
        st.session_state.quick_input = ""
        _handle_user_input(user_input)
        st.rerun()

    if user_input := st.chat_input("메시지를 입력하세요..."):
        _handle_user_input(user_input)


main()
