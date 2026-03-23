"""FastAPI 백엔드 — REST API + WebSocket."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from cron.jobs.morning_briefing import run_morning_briefing
from cron.jobs.weekly_report import run_weekly_report
from cron.scheduler import setup_scheduler
from tools.cost_tracker import get_cost_summary
from tools.notes import list_notes_raw, search_notes
from tools.papers import fetch_hf_daily_papers

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
    scheduler = setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Personal Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket ────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """백그라운드 작업 완료 알림을 실시간으로 전달한다."""
    await websocket.accept()
    _connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        if websocket in _connections:
            _connections.remove(websocket)


# ── REST API ─────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/notes")
async def get_notes(limit: int = 20) -> dict[str, object]:
    """최근 메모 목록을 반환한다."""
    return {"notes": list_notes_raw(limit=limit)}


@app.get("/api/notes/search")
async def search_notes_api(q: str, limit: int = 5) -> dict[str, object]:
    """메모를 검색한다."""
    return {"result": search_notes(q, limit=limit)}


@app.get("/api/costs")
async def get_costs() -> dict[str, str]:
    """이번 달 API 비용 요약을 반환한다."""
    return {"summary": get_cost_summary()}


@app.get("/api/papers/trending")
async def get_trending_papers(limit: int = 5) -> dict[str, str]:
    """HuggingFace 인기 논문을 반환한다."""
    return {"papers": fetch_hf_daily_papers(max_results=limit)}


@app.get("/api/briefing/latest")
async def get_latest_briefing() -> dict[str, object]:
    """가장 최근 아침 브리핑 메모를 반환한다."""
    notes = list_notes_raw(limit=30)
    briefings = [n for n in notes if "브리핑" in (n.get("tags") or "")]
    return {"briefing": briefings[0] if briefings else None}


@app.post("/api/broadcast")
async def broadcast_message(body: dict[str, str]) -> dict[str, str]:
    """WebSocket으로 메시지를 브로드캐스트한다 (내부 사용)."""
    await broadcast(json.dumps(body, ensure_ascii=False))
    return {"status": "sent"}


# ── 크론 수동 트리거 ──────────────────────────────────────────


@app.post("/api/cron/morning-briefing")
async def trigger_morning_briefing() -> dict[str, str]:
    """아침 브리핑을 즉시 실행한다 (수동 트리거)."""
    try:
        await run_morning_briefing()
        return {"status": "ok", "message": "아침 브리핑 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/cron/weekly-report")
async def trigger_weekly_report() -> dict[str, str]:
    """주간 리포트를 즉시 실행한다 (수동 트리거)."""
    try:
        await run_weekly_report()
        return {"status": "ok", "message": "주간 리포트 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
