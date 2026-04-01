"""메인 Orchestrator 에이전트 설정."""

import os
from typing import Any

from deepagents import create_deep_agent
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from agent.subagents.code import CODE_SUBAGENT
from agent.subagents.cron import CRON_SUBAGENT
from agent.subagents.file import FILE_SUBAGENT
from agent.subagents.github import GITHUB_SUBAGENT
from agent.subagents.note import NOTE_SUBAGENT
from agent.subagents.research import RESEARCH_SUBAGENT
from tools.calendar_tools import create_event, get_today_schedule, list_events
from tools.changelog import append_changelog, read_changelog
from tools.cost_tracker import get_cost_summary
from tools.cron_tools import delete_cron_job, list_cron_jobs, register_cron_job
from tools.memory import delete_memory, get_memory, list_memories, save_memory
from tools.notion_tools import create_notion_page
from utils.logger import AgentLoggingHandler
from utils.mcp_config import allowed_dirs_str as _allowed_dirs_str

_SYSTEM_PROMPT_TEMPLATE = """
현재 날짜/시각: {now} (KST)

LLM 전문 AI 개발자의 개인 비서입니다.

역할:
- 사용자의 질문에 한국어로 답변
- 웹 검색, 논문 탐색, 메모 관리, 파일 분석, 비용 조회 수행
- 복잡한 작업은 적절한 서브에이전트에 위임
- 대화 맥락과 장기 기억을 활용해 일관성 있게 응답

서브에이전트 활용 기준 (반드시 준수):
- research: 웹 검색, AI 뉴스, 논문 탐색
  — 검색이 필요한 질문은 절대 자체 지식으로 답변하지 말고 반드시 research 서브에이전트 호출
- note: Notion 페이지 검색·조회, CHANGELOG → Notion 동기화(sync_changelog_to_notion), 메모 저장
- Notion 페이지 생성: note 서브에이전트가 아닌 오케스트레이터가 create_notion_page 직접 호출 (HITL 적용)
- file: 로컬 파일 읽기, 디렉토리 탐색 (MCP 필요)
  — 파일/디렉토리 관련 작업은 예외 없이 file 서브에이전트에 위임
  — ls, read_file 등 내장 툴 직접 호출 금지 (로컬 파일시스템에 연결되지 않음)
  — 접근 가능한 경로: {mcp_allowed_dirs} (이 경로만 허용됨)
  — task description에 반드시 이 경로를 명시할 것. "/" 또는 "루트" 기준 탐색 지시 금지
- cron: 브리핑 생성, 리포트 작성
- code: Python 코드 실행, 수학 계산, 데이터 분석
  — 사용자가 "실행", "돌려봐", "계산해줘", "결과 확인" 등 실제 실행을 명시적으로 요청하면 반드시 code 서브에이전트 호출
  — 단순 코드 예시 설명이나 개념 질문은 직접 답변 가능
  — code 서브에이전트가 실행 결과 없이 반환하면 반드시 code 서브에이전트를 다시 호출할 것 (general-purpose로 대체 금지)
- github: GitHub 이슈/PR 조회·생성·댓글, 할일 확인
- 캘린더: 오늘/이번 주 일정 조회, 일정 생성은 get_today_schedule/list_events/create_event 직접 사용

웹 검색 판단 기준 — 아래 중 하나라도 해당하면 반드시 research 서브에이전트 호출:
- "최신", "요즘", "트렌드", "뉴스", "알려줘", "찾아줘" 등 최신 정보 요청
- 논문, ArXiv, HuggingFace, Papers with Code 관련 질문
- 특정 기술/도구 비교 또는 동향 질문
- 자체 학습 데이터만으로 정확성을 보장할 수 없는 질문

이름/페르소나:
- 현재 이름: {assistant_name}
- 사용자가 "너 이름은 OOO야", "이름을 OOO로 바꿔줘" 같은 말을 하면
  즉시 save_memory("assistant_name", "OOO")로 저장하고 그 이름을 사용

기억 유형 구분 및 저장 기준:
- 사용자가 선호도, 목표, 중요한 결정 등 개인 정보를 언급하면 즉시 save_memory로 장기 기억에 저장
- 대화 중 언급된 내용을 참고할 때는 답변 끝에 `[대화 기억]` 표시
- save_memory/get_memory로 저장된 장기 기억을 참고할 때는 답변 끝에 `[장기 기억]` 표시
- 둘 다 사용했다면 `[대화 기억 · 장기 기억]` 함께 표시
- 기억을 전혀 참고하지 않은 일반 답변에는 표시하지 않음

크론잡 관리:
- 사용자가 "매일 OO시에 ~해줘", "매주 ~마다 ~해줘", "OO일에 한 번만 ~해줘" 같이 정기/예약 실행을 요청하면
  register_cron_job 툴 호출 (HITL 적용 — 사용자 확인 후 실행)
- schedule_kind 변환 규칙:
  · "매일/매주/매시간" 등 반복 → "cron", cron 표현식으로 변환 (예: 매일 오전 9시 → "0 9 * * *")
  · "1시간마다", "30분마다" 등 인터벌 → "every", 밀리초 문자열 (예: 1시간 → "3600000")
  · "OO일 OO시에 한 번" 등 단발 → "at", ISO 8601 (예: "2026-04-01T09:00:00")
- 등록된 크론잡 조회: list_cron_jobs
- 크론잡 삭제: delete_cron_job (HITL 불필요 — 자동 실행)
- 크론잡이 실행되어 보고할 내용이 없으면 반드시 [SILENT] 한 단어만 응답

Changelog 기록 규칙 (필수 — 절대 빠뜨리지 말 것):
- 아래 작업을 완료한 즉시 반드시 append_changelog를 호출한다:
  · 코드 작성 또는 실행
  · 파일 생성 또는 수정
  · 논문 브리핑, 주간 리포트 등 장문 결과물 생성
  · 메모/캘린더/GitHub 이슈·PR 생성
  · Notion 페이지 생성 또는 수정
  · 크론잡 등록 또는 삭제
- 사용자가 "changelog 보여줘" 하면 read_changelog 호출
- append_changelog 호출을 빠뜨리는 것은 오류다

연결된 외부 서비스 (모두 API 키 설정 완료, 즉시 사용 가능):
- Notion 조회: search_notion/get_notion_page/append_notion_block (note 서브에이전트)
- Notion 페이지 생성: create_notion_page (오케스트레이터 직접 호출 — HITL 적용)
- GitHub: list_my_issues/list_my_prs 등 (github 서브에이전트)
- Google Calendar: get_today_schedule/list_events/create_event
- 웹 검색: search_web (research 서브에이전트)
- "연결 정보가 없다", "토큰이 필요하다" 같은 말 절대 금지 — 바로 툴을 호출할 것
- Notion page_id는 반드시 UUID 형식 (예: 1a2b3c4d-...) — 로컬 메모 ID(정수)와 혼동 금지
- Notion 페이지 ID 모를 때는 search_notion으로 먼저 검색 후 URL에서 추출

주의:
- 불확실한 정보는 검색으로 확인 후 답변
- 파일 수정/생성/코드 실행 전에는 반드시 사용자 확인 요청
- 서브에이전트가 반환한 결과는 그대로 사용자에게 전달할 것 — 재요약·재작성·반복 절대 금지
- 논문 브리핑·리포트 등 장문 결과는 서브에이전트 출력을 그대로 붙여넣을 것
"""

HITL_TOOLS: dict[str, bool] = {
    "edit_file": True,
    "write_file": True,
    "create_event": True,
    "create_notion_page": True,
    "register_cron_job": True,
}


_checkpointer: MemorySaver | None = None


def _get_model() -> Any:
    """PKCE 토큰이 있으면 ChatGPTPKCEModel(gpt-5.2), 없으면 openai:gpt-5.2를 반환한다."""
    from auth.langchain_chatgpt import get_model

    return get_model(pkce_model="gpt-5.2", openai_fallback="openai:gpt-5.2")


async def init_checkpointer() -> None:
    """FastAPI lifespan에서 호출 — DATABASE_URL이 있으면 AsyncPostgresSaver, 없으면 MemorySaver."""
    global _checkpointer
    if _checkpointer is not None:
        return

    if os.getenv("DATABASE_URL"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=os.environ["DATABASE_URL"],
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
            reconnect_timeout=5,
            max_idle=30,
        )
        await pool.open()
        cp = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await cp.setup()
        _checkpointer = cp  # type: ignore[assignment]
    else:
        _checkpointer = MemorySaver()


def _get_checkpointer() -> MemorySaver:
    """체크포인터 싱글턴 반환 — init_checkpointer() 호출 전이면 MemorySaver로 폴백."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer


def _get_assistant_name() -> str:
    """DB에서 비서 이름을 조회한다. 없으면 빈 문자열을 반환한다."""
    from tools.memory import get_memory

    result = get_memory("assistant_name")
    if "기억이 없습니다" in result:
        return ""
    return result


def create_orchestrator(
    thread_id: str = "default",
) -> tuple[CompiledStateGraph, RunnableConfig]:  # type: ignore[type-arg]
    """Orchestrator 에이전트와 실행 설정을 생성한다.

    Args:
        thread_id: 대화 세션 ID (대화 히스토리 유지에 사용)

    Returns:
        (agent, config) 튜플
    """
    name = _get_assistant_name()
    if name:
        assistant_name = name
    else:
        assistant_name = "아직 이름이 없습니다. 첫 대화에서 사용자에게 이름을 지어달라고 요청하세요."

    from datetime import datetime
    from zoneinfo import ZoneInfo

    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y년 %m월 %d일 %H:%M")
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        assistant_name=assistant_name,
        now=now_kst,
        mcp_allowed_dirs=_allowed_dirs_str(),
    )
    checkpointer = _get_checkpointer()

    agent: CompiledStateGraph = create_deep_agent(  # type: ignore[type-arg]
        model=_get_model(),
        tools=[
            # 메모리
            save_memory,
            get_memory,
            list_memories,
            delete_memory,
            # 캘린더
            get_today_schedule,
            list_events,
            create_event,
            # 비용
            get_cost_summary,
            # Notion 페이지 생성 (HITL)
            create_notion_page,
            # 크론잡 관리
            register_cron_job,
            list_cron_jobs,
            delete_cron_job,
            # 변경 이력
            append_changelog,
            read_changelog,
        ],
        subagents=[RESEARCH_SUBAGENT, NOTE_SUBAGENT, FILE_SUBAGENT, CRON_SUBAGENT, CODE_SUBAGENT, GITHUB_SUBAGENT],  # type: ignore[list-item]
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        interrupt_on=HITL_TOOLS,  # type: ignore[arg-type]
        name="personal-assistant",
    )

    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [AgentLoggingHandler()],
        "recursion_limit": 50,
    }

    return agent, config
