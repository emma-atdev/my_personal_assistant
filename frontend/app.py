"""Streamlit 채팅 UI — 개인 비서 프론트엔드."""

import asyncio
import queue
import threading
import time
from collections.abc import AsyncGenerator, Generator
from datetime import date, datetime
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()  # .env 로드 후 에이전트 임포트

from agent.orchestrator import create_orchestrator, get_backend_loop  # noqa: E402

st.set_page_config(page_title="개인 비서", page_icon="🤖", layout="wide")

# ── 상수 ─────────────────────────────────────────────────────

_QUICK_ACTIONS = [
    ("오늘 일정", "오늘 일정 알려줘"),
    ("이번 주 일정", "이번 주 일정 알려줘"),
    ("논문 브리핑", "최신 AI 논문 브리핑해줘"),
    ("Changelog", "changelog 보여줘"),
    ("API 비용", "이번 달 API 비용 알려줘"),
]

_TOOL_LABELS: dict[str, str] = {
    "task": "서브에이전트에서 작업 중입니다.",
    "tavily_search_results_json": "웹에서 정보를 검색 중입니다.",
    "search_web": "웹에서 정보를 검색 중입니다.",
    "fetch_arxiv_papers": "ArXiv에서 논문을 검색 중입니다.",
    "fetch_hf_daily_papers": "HuggingFace에서 논문을 가져오는 중입니다.",
    "fetch_pwc_trending": "Papers with Code에서 트렌드를 조회 중입니다.",
    "search_notes": "메모를 검색 중입니다.",
    "create_note": "메모를 저장 중입니다.",
    "list_notes": "메모 목록을 불러오는 중입니다.",
    "save_memory": "기억을 저장 중입니다.",
    "get_memory": "기억을 조회 중입니다.",
    "list_memories": "기억 목록을 불러오는 중입니다.",
    "delete_memory": "기억을 삭제 중입니다.",
    "list_events": "Google Calendar에서 일정을 조회 중입니다.",
    "create_event": "Google Calendar에 일정을 생성 중입니다.",
    "get_today_schedule": "오늘 일정을 확인 중입니다.",
    "get_cost_summary": "API 비용을 확인 중입니다.",
    "append_changelog": "Changelog에 기록 중입니다.",
    "read_changelog": "Changelog를 불러오는 중입니다.",
    "list_my_issues": "GitHub에서 이슈 목록을 조회 중입니다.",
    "list_my_prs": "GitHub에서 PR 목록을 조회 중입니다.",
    "get_issue": "GitHub 이슈 내용을 확인 중입니다.",
    "create_issue": "GitHub에 이슈를 생성 중입니다.",
    "comment_on_issue": "GitHub 이슈에 댓글을 작성 중입니다.",
    "list_repo_issues": "GitHub 레포 이슈를 조회 중입니다.",
    "search_notion": "Notion에서 페이지를 검색 중입니다.",
    "get_notion_page": "Notion 페이지를 불러오는 중입니다.",
    "create_notion_page": "Notion에 페이지를 생성 중입니다.",
    "append_notion_block": "Notion 페이지에 내용을 추가 중입니다.",
    "sync_changelog_to_notion": "Notion에 Changelog를 동기화 중입니다.",
    "execute": "코드를 실행 중입니다.",
    "write_file": "파일을 작성 중입니다.",
    "edit_file": "파일을 수정 중입니다.",
    "read_file": "파일을 읽는 중입니다.",
}


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, f"{name} 실행 중입니다.")


# ── 세션 초기화 ───────────────────────────────────────────────


def _load_messages_from_state() -> list[dict[str, str]]:
    """현재 thread의 LangGraph 상태에서 메시지를 복원한다."""
    import asyncio

    loop = get_backend_loop()
    future = asyncio.run_coroutine_threadsafe(st.session_state.agent.aget_state(st.session_state.config), loop)
    state = future.result(timeout=10)
    messages = state.values.get("messages", [])

    result = []
    for m in messages:
        if isinstance(m, HumanMessage):
            result.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage) and m.content:
            content = m.content
            if isinstance(content, list):
                text = " ".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")
            else:
                text = str(content)
            if text:
                result.append({"role": "assistant", "content": text})
    return result


def _switch_conversation(thread_id: str) -> None:
    """thread_id로 대화를 전환하고 메시지를 복원한다."""
    _, config = create_orchestrator(thread_id=thread_id)
    st.session_state.config = config
    st.session_state.thread_id = thread_id
    st.session_state.messages = _load_messages_from_state()
    st.session_state.total_tokens = {"input": 0, "output": 0}


def _init_session() -> None:
    from tools.conversations import create_conversation, list_conversations

    if "agent" not in st.session_state:
        agent, _ = create_orchestrator(thread_id="default")
        st.session_state.agent = agent

    if "thread_id" not in st.session_state:
        convs = list_conversations(limit=20)
        # 제목이 있는 대화 우선, 없으면 '새 채팅' 사용, 없으면 생성
        real = [c for c in convs if c["title"] != "새 채팅"]
        if real:
            thread_id = real[0]["thread_id"]
        elif convs:
            thread_id = convs[0]["thread_id"]
        else:
            thread_id = create_conversation("새 채팅")
        st.session_state.thread_id = thread_id

    if "config" not in st.session_state:
        _, config = create_orchestrator(thread_id=st.session_state.thread_id)
        st.session_state.config = config

    if "messages" not in st.session_state:
        st.session_state.messages = _load_messages_from_state()
    if "quick_input" not in st.session_state:
        st.session_state.quick_input = ""
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = {"input": 0, "output": 0}
    if "briefing_read" not in st.session_state:
        st.session_state.briefing_read = False
    if "weekly_report_read" not in st.session_state:
        st.session_state.weekly_report_read = False

    if "today_briefing" not in st.session_state or "this_week_report" not in st.session_state:
        from datetime import timedelta

        from tools.notion_tools import search_notion

        today = date.today()
        today_str = today.strftime("%Y-%m-%d")
        week_label = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

        def _extract_notion_url(result: str, title: str) -> str | None:
            """검색 결과에서 Notion URL을 추출한다. 제목이 일치하는 항목의 URL만 반환."""
            lines = result.split("\n")
            for i, line in enumerate(lines):
                if title in line:
                    for check in lines[i : i + 2]:
                        for part in check.split():
                            if part.startswith("https://www.notion.so/"):
                                return part.strip("()[]")
            return None

        briefing_title = f"아침 브리핑 {today_str}"
        try:
            st.session_state.today_briefing = _extract_notion_url(search_notion(briefing_title), briefing_title)
        except Exception:
            st.session_state.today_briefing = None

        report_title = f"주간 리포트 {week_label}"
        try:
            st.session_state.this_week_report = _extract_notion_url(search_notion(report_title), report_title)
        except Exception:
            st.session_state.this_week_report = None
    if "conv_renaming" not in st.session_state:
        st.session_state.conv_renaming = None  # 이름 수정 중인 thread_id


# ── 이벤트 스트리밍 ───────────────────────────────────────────


async def _stream_events(agent: Any, config: Any, user_input: str) -> AsyncGenerator[dict[str, Any]]:
    """에이전트 이벤트를 스트리밍한다."""
    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=user_input)]},
        config,
        version="v2",
    ):
        etype = event["event"]

        if etype == "on_chat_model_start":
            metadata = event.get("metadata", {})
            ns = metadata.get("checkpoint_ns", "")
            if ns.startswith("tools:"):
                yield {"type": "status", "label": "서브에이전트에서 분석 중입니다."}
            else:
                yield {"type": "status", "label": "orchestrator_llm_start"}

        elif etype == "on_chat_model_stream":
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
            name = event.get("name", "")
            args = event.get("data", {}).get("input", {}) if name == "task" else {}
            yield {"type": "tool_start", "name": name, "args": args}

        elif etype == "on_tool_end":
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
    loop = get_backend_loop()

    async def _producer() -> None:
        import traceback

        try:
            async for ev in _stream_events(agent, config, user_input):
                event_queue.put(ev)
        except Exception as e:  # noqa: BLE001
            msg = traceback.format_exc() or f"{type(e).__name__}: {e!r}"
            event_queue.put({"type": "error", "message": msg})
        finally:
            event_queue.put(None)

    asyncio.run_coroutine_threadsafe(_producer(), loop)

    stop_tick = threading.Event()

    def _ticker() -> None:
        while not stop_tick.is_set():
            time.sleep(0.5)
            event_queue.put({"type": "tick"})

    tick_thread = threading.Thread(target=_ticker, daemon=True)
    tick_thread.start()

    while True:
        ev = event_queue.get()
        if ev is None:
            stop_tick.set()
            break
        yield ev


# ── HITL ─────────────────────────────────────────────────────


@st.dialog("대화 초기화")
def _confirm_reset_dialog() -> None:
    st.warning("현재 대화가 완전히 삭제됩니다. 계속하시겠습니까?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("삭제", use_container_width=True, type="primary"):
            from tools.conversations import create_conversation, delete_conversation, list_conversations

            delete_conversation(st.session_state.thread_id)
            remaining = [c for c in list_conversations(limit=20) if c["title"] != "새 채팅"]
            if remaining:
                next_id = remaining[0]["thread_id"]
            else:
                next_id = create_conversation("새 채팅")
            _switch_conversation(next_id)
            st.session_state.total_tokens = {"input": 0, "output": 0}
            st.session_state.pop("confirm_reset", None)
            st.rerun()
    with col2:
        if st.button("취소", use_container_width=True):
            st.session_state.pop("confirm_reset", None)
            st.rerun()


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
        status = st.status("요청을 분석 중입니다.", expanded=False)
        timer_box = st.empty()
        text_box = st.empty()

        full_response = ""
        session_tokens = {"input": 0, "output": 0}
        start_time = time.time()
        tool_called = False

        # 단계별 소요 시간 추적
        step_placeholder: Any = None
        step_label: str = ""
        step_start: float = 0.0
        steps: list[dict[str, Any]] = []

        def _start_step(label: str) -> None:
            nonlocal step_placeholder, step_label, step_start
            # 이전 단계 완료 시간 기록
            if step_placeholder is not None:
                step_elapsed = int(time.time() - step_start)
                step_placeholder.caption(f"{step_label} — {step_elapsed}초")
                steps.append({"label": step_label, "elapsed": step_elapsed})
            step_label = label
            step_start = time.time()
            with status:
                step_placeholder = st.empty()
                step_placeholder.caption(label)

        for ev in _run_events(user_input):
            elapsed = int(time.time() - start_time)
            timer_box.caption(f"⏱ {elapsed}초 경과")
            if ev["type"] == "tick":
                continue
            elif ev["type"] == "error":
                st.error(f"오류: {ev['message']}")
                break
            elif ev["type"] == "token":
                full_response += ev["text"]
                text_box.markdown(full_response + "▌")
            elif ev["type"] == "status":
                if ev["label"] == "orchestrator_llm_start":
                    label = "답변을 작성 중입니다." if tool_called else "요청을 분석 중입니다."
                else:
                    label = ev["label"]
                status.update(label=label, state="running", expanded=False)
                _start_step(label)
            elif ev["type"] == "tool_start":
                tool_called = True
                name = ev["name"]
                if name == "task":
                    subagent = ev.get("args", {}).get("subagent_type", "")
                    _subagent_labels = {
                        "research": "research 에이전트에서 검색 중입니다.",
                        "note": "note 에이전트에서 메모를 처리 중입니다.",
                        "github": "github 에이전트에서 작업 중입니다.",
                        "code": "code 에이전트에서 코드를 실행 중입니다.",
                        "file": "file 에이전트에서 파일을 읽는 중입니다.",
                        "cron": "cron 에이전트에서 리포트를 생성 중입니다.",
                    }
                    label = _subagent_labels.get(subagent, "서브에이전트에서 작업 중입니다.")
                else:
                    label = _tool_label(name)
                status.update(label=label, state="running", expanded=False)
                _start_step(label)
            elif ev["type"] == "usage":
                session_tokens["input"] += ev["input_tokens"]
                session_tokens["output"] += ev["output_tokens"]

        # 마지막 단계 완료 시간 기록
        if step_placeholder is not None:
            step_elapsed = int(time.time() - step_start)
            step_placeholder.caption(f"{step_label} — {step_elapsed}초")
            steps.append({"label": step_label, "elapsed": step_elapsed})

        elapsed = int(time.time() - start_time)
        status.update(label=f"완료 ({elapsed}초)", state="complete", expanded=False)
        timer_box.empty()
        text_box.markdown(full_response)

        # 이번 응답 토큰 표시
        total = session_tokens["input"] + session_tokens["output"]
        if total > 0:
            st.caption(f"↑ {session_tokens['input']:,} · ↓ {session_tokens['output']:,} 토큰")
            st.session_state.total_tokens["input"] += session_tokens["input"]
            st.session_state.total_tokens["output"] += session_tokens["output"]

    st.session_state.messages.append(
        {"role": "assistant", "content": full_response, "elapsed": elapsed, "steps": steps}
    )

    # 첫 메시지면 대화 제목 자동 설정
    if len(st.session_state.messages) == 2:  # user + assistant
        from tools.conversations import update_conversation_title

        title = user_input[:30] + ("..." if len(user_input) > 30 else "")
        update_conversation_title(st.session_state.thread_id, title)

    # 대화 updated_at 갱신
    from tools.conversations import touch_conversation

    touch_conversation(st.session_state.thread_id)

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

    st.markdown(
        """
        <style>
        *, *::before, *::after {
            transition: none !important;
            animation-duration: 0.001s !important;
        }
        [class*="st-key-conv_"] button,
        div.current-conv > div > button {
            background: transparent !important;
            border: 1px solid transparent !important;
            text-align: left !important;
            justify-content: flex-start !important;
            align-items: flex-start !important;
            color: inherit !important;
            box-shadow: none !important;
            padding-left: 8px !important;
        }
        [class*="st-key-conv_"] button > div,
        div.current-conv > div > button > div {
            justify-content: flex-start !important;
            text-align: left !important;
            width: 100% !important;
        }
        [class*="st-key-conv_"] button:hover,
        div.current-conv > div > button:hover {
            background: rgba(150,150,150,0.1) !important;
        }
        div.current-conv > div > button {
            font-weight: 700 !important;
        }
        [data-testid="stPopover"] > button {
            padding: 2px 6px !important;
            min-height: unset !important;
            height: 28px !important;
            font-size: 13px !important;
        }
        [data-testid="stPopoverButton"] div:has(> span > [data-testid="stIconMaterial"]) {
            display: none !important;
        }
        [data-testid="stPopoverButton"] > div {
            margin-right: 0 !important;
            justify-content: center !important;
        }
        [data-testid="stPopoverBody"] {
            min-width: unset !important;
            width: fit-content !important;
        }
        [data-testid="stPopoverBody"] > div {
            padding: 4px !important;
        }
        [data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {
            gap: 2px !important;
        }
        [data-testid="stPopover"] [data-testid="stBaseButton-secondary"] {
            padding: 2px 8px !important;
            min-height: unset !important;
            height: 26px !important;
            font-size: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("## 최정짱 비서")
        st.caption(
            "웹 검색 · 논문 탐색 · 메모 관리 · Notion · Google Calendar · GitHub · Python 코드 실행 · API 비용 확인"
        )

        total_in = st.session_state.total_tokens["input"]
        total_out = st.session_state.total_tokens["output"]
        if total_in + total_out > 0:
            st.caption(f"세션 토큰  ↑ {total_in:,} · ↓ {total_out:,}")

        st.divider()

        # ── 대화 목록 ─────────────────────────────────────────────
        from tools.conversations import create_conversation, list_conversations

        has_messages = bool(st.session_state.messages)
        if st.button("➕ 새 채팅", use_container_width=True, disabled=not has_messages):
            new_id = create_conversation("새 채팅")
            _switch_conversation(new_id)
            st.session_state.conv_menu = None
            st.rerun()

        convs = list_conversations(limit=20)
        _default_title = "새 채팅"
        for conv in convs:
            tid = conv["thread_id"]
            title = conv["title"]
            if title == _default_title:
                continue
            is_current = tid == st.session_state.thread_id

            col_title, col_menu = st.columns([8, 1])
            with col_title:
                if is_current:
                    st.markdown(
                        f'<a style="font-weight:700;text-decoration:none;color:inherit;'
                        f'display:block;padding:6px 8px;">{title}</a>',
                        unsafe_allow_html=True,
                    )
                elif st.button(title, key=f"conv_{tid}", use_container_width=True):
                    _switch_conversation(tid)
                    st.rerun()

            with col_menu:
                with st.popover("⋮"):
                    if st.button("이름 수정", key=f"rename_{tid}", use_container_width=True):
                        st.session_state.conv_renaming = tid
                        st.rerun()
                    if st.button("삭제", key=f"delete_{tid}", use_container_width=True):
                        from tools.conversations import delete_conversation

                        delete_conversation(tid)
                        if is_current:
                            remaining = [c for c in convs if c["thread_id"] != tid]
                            if remaining:
                                _switch_conversation(remaining[0]["thread_id"])
                            else:
                                new_id = create_conversation("새 채팅")
                                _switch_conversation(new_id)
                        st.rerun()

            # 이름 수정 인라인 폼
            if st.session_state.conv_renaming == tid:
                new_title = st.text_input(
                    "새 이름", value=title, key=f"rename_input_{tid}", label_visibility="collapsed"
                )
                rc1, rc2 = st.columns(2)
                with rc1:
                    if st.button("확인", key=f"rename_ok_{tid}", use_container_width=True):
                        from tools.conversations import update_conversation_title

                        update_conversation_title(tid, new_title)
                        st.session_state.conv_renaming = None
                        st.rerun()
                with rc2:
                    if st.button("취소", key=f"rename_cancel_{tid}", use_container_width=True):
                        st.session_state.conv_renaming = None
                        st.rerun()

        st.divider()

        # ── 브리핑 / 주간 리포트 알림 ────────────────────────────
        has_notification = False

        if not st.session_state.briefing_read and st.session_state.today_briefing:
            has_notification = True
            with st.container(border=True):
                st.caption("오늘의 브리핑")
                st.markdown(f"📬 **아침 브리핑 {date.today().strftime('%m월 %d일')}**")
                _c1, _c2 = st.columns([3, 2])
                with _c1:
                    st.link_button(
                        "Notion 열기",
                        st.session_state.today_briefing,
                        use_container_width=True,
                        type="primary",
                    )
                with _c2:
                    if st.button("읽음", key="briefing_read_btn", use_container_width=True):
                        st.session_state.briefing_read = True
                        st.rerun()

        if not st.session_state.weekly_report_read:
            from datetime import timedelta

            _ws = date.today() - timedelta(days=date.today().weekday())
            _week_num = (_ws.day - 1) // 7 + 1
            _week_display = f"{_ws.month}월 {_week_num}번째 주"
            _report_url = st.session_state.this_week_report
            if _report_url:
                has_notification = True
            with st.container(border=True):
                st.caption("이번 주 리포트")
                st.markdown(f"📊 **주간 리포트 - {_week_display}**")
                _c1, _c2 = st.columns([3, 2])
                with _c1:
                    st.link_button(
                        "Notion 열기",
                        _report_url or "#",
                        use_container_width=True,
                        type="primary",
                        disabled=not _report_url,
                    )
                with _c2:
                    if st.button("읽음", key="report_read_btn", use_container_width=True, disabled=not _report_url):
                        st.session_state.weekly_report_read = True
                        st.rerun()

        if has_notification:
            st.divider()

        st.markdown("**⚡ 빠른 실행**")
        for label, query in _QUICK_ACTIONS:
            if st.button(label, use_container_width=True, key=f"quick_{label}"):
                st.session_state.quick_input = query

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ 초기화", use_container_width=True):
                st.session_state.confirm_reset = True
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
            if msg["role"] == "assistant" and msg.get("steps"):
                with st.status(f"완료 ({msg.get('elapsed', 0)}초)", state="complete", expanded=False):
                    for step in msg["steps"]:
                        st.caption(f"{step['label']} — {step['elapsed']}초")
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("elapsed") and not msg.get("steps"):
                st.caption(f"완료 ({msg['elapsed']}초)")

    # 빠른 실행 버튼 쿼리 처리
    if st.session_state.quick_input:
        user_input = st.session_state.quick_input
        st.session_state.quick_input = ""
        _handle_user_input(user_input)
        st.rerun()

    if st.session_state.get("confirm_reset"):
        _confirm_reset_dialog()

    if user_input := st.chat_input("메시지를 입력하세요..."):
        _handle_user_input(user_input)
        st.rerun()


main()
