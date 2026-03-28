"""사용자 정의 크론잡 실행 — 오케스트레이터 호출 후 WebSocket 브로드캐스트."""

import asyncio

from langchain_core.messages import AIMessage


async def run_user_job(job_id: str, task: str, timeout_seconds: int = 300) -> None:
    """사용자 정의 크론잡을 실행한다.

    오케스트레이터에 task를 전달하고 결과를 WebSocket으로 브로드캐스트한다.
    [SILENT] 응답이면 푸시하지 않는다. 연속 실패 3회 시 잡을 자동 비활성화한다.
    at(단발) 잡은 실행 후 DB와 스케줄러에서 자동 삭제한다.
    """
    from storage.cron_jobs import delete_cron_job, increment_error, load_cron_jobs, reset_errors

    # at(단발) 잡 여부 확인
    jobs = load_cron_jobs()
    job_meta = next((j for j in jobs if j["job_id"] == job_id), None)
    is_one_shot = job_meta is not None and job_meta["schedule_kind"] == "at"

    print(f"[user_job] {job_id} 실행 시작 — task: {task[:50]}")
    try:
        result = await asyncio.wait_for(_invoke(job_id, task), timeout=timeout_seconds)
    except TimeoutError:
        print(f"[user_job] {job_id} 타임아웃 ({timeout_seconds}s)")
        count = increment_error(job_id)
        if count >= 3:  # noqa: PLR2004
            print(f"[user_job] {job_id} 연속 실패 {count}회 — 비활성화")
        return
    except Exception as e:  # noqa: BLE001
        print(f"[user_job] {job_id} 실행 오류: {e}")
        count = increment_error(job_id)
        if count >= 3:  # noqa: PLR2004
            print(f"[user_job] {job_id} 연속 실패 {count}회 — 비활성화")
        return

    print(f"[user_job] {job_id} _invoke 결과: {result[:80]!r}")
    reset_errors(job_id)

    if "[SILENT]" not in result:
        import json

        from backend.app import broadcast, _connections
        print(f"[user_job] broadcast 호출 — 연결된 클라이언트 수: {len(_connections)}")
        await broadcast(json.dumps({"type": "cron", "job_id": job_id, "message": result}, ensure_ascii=False))

    if is_one_shot:
        delete_cron_job(job_id)
        from cron.scheduler import remove_user_job
        remove_user_job(job_id)
        print(f"[user_job] {job_id} 단발 잡 완료 — 삭제")


async def _invoke(job_id: str, task: str) -> str:
    """오케스트레이터를 호출하고 마지막 AIMessage 텍스트를 반환한다."""
    from agent.orchestrator import create_orchestrator

    agent, config = create_orchestrator(thread_id=f"cron_{job_id}")
    from langchain_core.messages import HumanMessage

    result = await agent.ainvoke({"messages": [HumanMessage(content=task)]}, config)
    messages = result.get("messages", [])
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            content = m.content
            if isinstance(content, list):
                return " ".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")
            return str(content)
    return "[SILENT]"
