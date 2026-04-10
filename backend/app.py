"""FastAPI 백엔드 — REST API + WebSocket."""

import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # 에이전트 모듈 임포트 전에 환경변수 로드

from fastapi import BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agent.orchestrator import create_orchestrator, init_checkpointer  # noqa: E402
from agent.subagents.code import stop_sandbox  # noqa: E402
from cron.jobs.morning_briefing import run_morning_briefing  # noqa: E402
from cron.jobs.weekly_report import run_weekly_report  # noqa: E402
from cron.scheduler import load_user_jobs_from_db, setup_scheduler  # noqa: E402
from tools.cost_tracker import get_cost_summary  # noqa: E402
from tools.papers import fetch_hf_daily_papers  # noqa: E402

# WebSocket 연결 풀
_connections: list[WebSocket] = []


async def broadcast(message: str) -> None:
    """모든 WebSocket 클라이언트에 메시지를 전송한다."""
    for ws in list(_connections):
        try:
            await ws.send_text(message)
        except Exception:
            _connections.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await init_checkpointer()
    scheduler = setup_scheduler()
    scheduler.start()
    load_user_jobs_from_db()
    yield
    scheduler.shutdown()
    stop_sandbox()


app = FastAPI(title="Personal Assistant API", lifespan=lifespan)

_MPA_API_KEY = os.getenv("MPA_API_KEY", "")

_AUTH_SKIP_PATHS: frozenset[str] = frozenset({"/api/health", "/docs", "/openapi.json", "/ws"})


@app.middleware("http")
async def api_key_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
    """API 키 인증 미들웨어. MPA_API_KEY가 비어있으면 인증 비활성화."""
    if not _MPA_API_KEY:
        return await call_next(request)

    if request.url.path in _AUTH_SKIP_PATHS:
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    if auth == f"Bearer {_MPA_API_KEY}":
        return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "Unauthorized"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic 모델 ────────────────────────────────────────────


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    confirmed: bool
    tool_name: str
    tool_args: dict[str, Any]
    tool_call_id: str


# ── 헬퍼 ────────────────────────────────────────────────────


def _process_event(event: Any) -> dict[str, Any] | None:
    """astream_events 이벤트를 프론트엔드 전송용 dict로 변환한다. 불필요한 이벤트는 None."""
    etype = event["event"]

    if etype == "on_chat_model_start":
        metadata = event.get("metadata", {})
        ns = metadata.get("checkpoint_ns", "")
        if ns.startswith("tools:"):
            return {"type": "status", "label": "서브에이전트에서 분석 중입니다."}
        return {"type": "status", "label": "orchestrator_llm_start"}

    elif etype == "on_chat_model_stream":
        metadata = event.get("metadata", {})
        if metadata.get("checkpoint_ns", "").startswith("tools:"):
            return None
        chunk = event["data"].get("chunk")
        if not chunk or not hasattr(chunk, "content"):
            return None
        content = chunk.content
        if isinstance(content, str) and content:
            return {"type": "token", "text": content}
        elif isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            text = "".join(texts)
            if text:
                return {"type": "token", "text": text}

    elif etype == "on_tool_start":
        name = event.get("name", "")
        args = event.get("data", {}).get("input", {}) if name == "task" else {}
        return {"type": "tool_start", "name": name, "args": args}

    elif etype == "on_tool_end":
        return {"type": "tool_end", "name": event.get("name", "")}

    elif etype == "on_chat_model_end":
        output = event["data"].get("output")
        if output and hasattr(output, "usage_metadata") and output.usage_metadata:
            usage = output.usage_metadata
            if isinstance(usage, dict):
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
            else:
                inp = getattr(usage, "input_tokens", 0)
                out = getattr(usage, "output_tokens", 0)
            ns = event.get("metadata", {}).get("checkpoint_ns", "")
            result: dict[str, Any] = {"type": "usage", "input_tokens": inp, "output_tokens": out}
            if not ns.startswith("tools:"):
                from auth.langchain_chatgpt import _PKCE_TOKENS_AVAILABLE

                model_name = getattr(output, "response_metadata", {}).get("model_name", "") or ""
                result["context_tokens"] = inp
                result["is_pkce"] = bool(_PKCE_TOKENS_AVAILABLE)
                result["model_name"] = model_name
            return result

    return None


def _extract_hitl_from_state(state: Any) -> dict[str, Any]:
    """StateSnapshot의 tasks/interrupts에서 HITL 정보를 추출한다.

    서브에이전트 레벨 interrupt도 감지 가능.
    """
    for task in getattr(state, "tasks", ()):
        for intr in getattr(task, "interrupts", ()):
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and "action_requests" in value:
                actions = value["action_requests"]
                if actions:
                    action = actions[0]
                    return {
                        "type": "hitl",
                        "tool_name": action.get("name", "알 수 없는 작업"),
                        "tool_args": action.get("args", {}),
                        "tool_call_id": "",
                    }
    return {"type": "hitl", "tool_name": "알 수 없는 작업", "tool_args": {}, "tool_call_id": ""}


def _extract_text(messages: list[Any]) -> str:
    """메시지 목록에서 마지막 AIMessage 텍스트를 추출한다."""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            content = m.content
            if isinstance(content, list):
                return " ".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")
            return str(content)
    return ""


# ── WebSocket ────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """백그라운드 작업 완료 알림을 실시간으로 전달한다."""
    if _MPA_API_KEY:
        token = websocket.query_params.get("token", "")
        if token != _MPA_API_KEY:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    await websocket.accept()
    _connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        if websocket in _connections:
            _connections.remove(websocket)


# ── 채팅 API ─────────────────────────────────────────────────


@app.post("/api/chat")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """사용자 메시지를 받아 에이전트 응답을 SSE로 스트리밍한다."""
    agent, config = create_orchestrator(thread_id=body.thread_id)

    async def event_generator() -> AsyncGenerator[str]:
        try:
            from agent.router import route

            try:
                state = await agent.aget_state(config)
                history = state.values.get("messages", [])
            except Exception:
                history = []
            route_result = await route(body.message, history)

            if route_result["type"] == "simple":
                # 경량 모델 즉답 — 오케스트레이터 없이 바로 스트리밍
                response: str = route_result.get("response", "")
                yield f"data: {json.dumps({'type': 'token', 'text': response}, ensure_ascii=False)}\n\n"
                # 대화 히스토리 유지를 위해 LangGraph state에 저장
                try:
                    await agent.aupdate_state(
                        config,
                        {"messages": [HumanMessage(content=body.message), AIMessage(content=response)]},
                        as_node="model",
                    )
                except Exception as update_err:
                    from utils.logger import agent_logger

                    agent_logger.warning("simple 응답 state 저장 실패 (히스토리 미반영): %s", update_err)
            else:
                # complex — 재작성된 쿼리로 오케스트레이터 호출
                rewritten = route_result.get("rewritten") or body.message
                async for event in agent.astream_events(
                    {"messages": [HumanMessage(content=rewritten)]},
                    config,
                    version="v2",
                ):
                    chunk = _process_event(event)
                    if chunk:
                        if "context_tokens" in chunk:
                            from tools.conversations import update_context_tokens

                            update_context_tokens(body.thread_id, chunk["context_tokens"])
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                state = await agent.aget_state(config)
                if state.next:
                    hitl_event = _extract_hitl_from_state(state)
                    yield f"data: {json.dumps(hitl_event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/chat/resume")
async def chat_resume(body: ResumeRequest) -> dict[str, str]:
    """HITL 확인/취소 후 에이전트를 재개한다."""
    from langgraph.types import Command

    agent, config = create_orchestrator(thread_id=body.thread_id)

    decision = "approve" if body.confirmed else "reject"
    result = await agent.ainvoke(Command(resume={"decisions": [{"type": decision}]}), config)
    all_messages = result.get("messages", [])
    response = _extract_text(all_messages)

    return {"response": response or "완료됐습니다."}


@app.get("/api/chat/messages/{thread_id}")
async def get_messages(thread_id: str) -> dict[str, Any]:
    """thread_id에 해당하는 대화 히스토리를 반환한다 (페이지 새로고침 복원용)."""
    from tools.conversations import load_message_metadata

    agent, config = create_orchestrator(thread_id=thread_id)
    state = await agent.aget_state(config)
    messages = state.values.get("messages", [])
    metadata = load_message_metadata(thread_id)

    result: list[dict[str, Any]] = []
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
                idx = len(result)
                msg_meta = metadata.get(str(idx), {})
                result.append(
                    {
                        "role": "assistant",
                        "content": text,
                        "elapsed": msg_meta.get("elapsed", 0),
                        "steps": msg_meta.get("steps", []),
                    }
                )

    return {"messages": result}


# ── REST API ─────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/context-tokens/{thread_id}")
async def get_context_tokens(thread_id: str) -> dict[str, int]:
    """thread_id 대화의 마지막 컨텍스트 토큰 수를 반환한다."""
    from tools.conversations import get_context_tokens as _get

    return {"context_tokens": _get(thread_id)}


@app.get("/api/auth-mode")
async def auth_mode() -> dict[str, bool]:
    """현재 인증 방식을 반환한다 (PKCE OAuth 여부)."""
    try:
        from auth.chatgpt_pkce import load_tokens

        tokens = load_tokens()
        is_pkce = bool(tokens and tokens.get("access_token"))
    except Exception:
        is_pkce = False
    return {"is_pkce": is_pkce}


@app.get("/api/costs")
async def get_costs() -> dict[str, str]:
    """이번 달 API 비용 요약을 반환한다."""
    return {"summary": get_cost_summary()}


@app.get("/api/papers/trending")
async def get_trending_papers(limit: int = 5) -> dict[str, str]:
    """HuggingFace 인기 논문을 반환한다."""
    return {"papers": fetch_hf_daily_papers(max_results=limit)}


@app.post("/api/broadcast")
async def broadcast_message(body: dict[str, str]) -> dict[str, str]:
    """WebSocket으로 메시지를 브로드캐스트한다 (내부 사용)."""
    await broadcast(json.dumps(body, ensure_ascii=False))
    return {"status": "sent"}


# ── 크론 수동 트리거 ──────────────────────────────────────────


@app.post("/api/cron/morning-briefing")
async def trigger_morning_briefing(background_tasks: BackgroundTasks) -> dict[str, str]:
    """아침 브리핑을 백그라운드에서 실행한다 (수동 트리거)."""
    background_tasks.add_task(run_morning_briefing)
    return {"status": "ok", "message": "아침 브리핑 시작됨 (백그라운드 실행 중)"}


@app.post("/api/cron/weekly-report")
async def trigger_weekly_report(background_tasks: BackgroundTasks) -> dict[str, str]:
    """주간 리포트를 백그라운드에서 실행한다 (수동 트리거)."""
    background_tasks.add_task(run_weekly_report)
    return {"status": "ok", "message": "주간 리포트 시작됨 (백그라운드 실행 중)"}
