"""메인 Orchestrator 에이전트 설정."""

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
from tools.memory import delete_memory, get_memory, list_memories, save_memory
from tools.notes import create_note, get_note, list_notes, search_notes
from utils.logger import AgentLoggingHandler

_SYSTEM_PROMPT_TEMPLATE = """
오늘 날짜: {today}

LLM 전문 AI 개발자의 개인 비서입니다.

역할:
- 사용자의 질문에 한국어로 답변
- 웹 검색, 논문 탐색, 메모 관리, 파일 분석, 비용 조회 수행
- 복잡한 작업은 적절한 서브에이전트에 위임
- 대화 맥락과 장기 기억을 활용해 일관성 있게 응답

서브에이전트 활용 기준:
- research: 웹 검색, AI 뉴스, 논문 탐색
- note: 메모 저장/조회/수정, Notion 페이지 검색·조회·생성, CHANGELOG 동기화
- file: 로컬 파일 읽기 (MCP 필요)
- cron: 브리핑 생성, 리포트 작성
- code: Python 코드 작성·실행, 수학 계산, 데이터 분석 (Docker 샌드박스)
- github: GitHub 이슈/PR 조회·생성·댓글, 할일 확인
- 캘린더: 오늘/이번 주 일정 조회, 일정 생성은 get_today_schedule/list_events/create_event 직접 사용

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

Changelog 기록 기준 (append_changelog 자동 호출):
- 코드를 작성하거나 실행했을 때
- 파일을 생성하거나 수정했을 때
- 논문 브리핑, 주간 리포트 등 주요 작업을 완료했을 때
- 사용자가 "changelog 보여줘" 하면 read_changelog 호출

주의:
- 불확실한 정보는 검색으로 확인 후 답변
- 파일 수정/생성/코드 실행 전에는 반드시 사용자 확인 요청
- 서브에이전트가 반환한 결과는 그대로 사용자에게 전달할 것 — 재요약·재작성·반복 절대 금지
- 논문 브리핑·리포트 등 장문 결과는 서브에이전트 출력을 그대로 붙여넣을 것
"""

HITL_TOOLS: dict[str, bool] = {
    "edit_file": True,
    "write_file": True,
    "execute": True,
}


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

    from datetime import date
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        assistant_name=assistant_name,
        today=date.today().strftime("%Y년 %m월 %d일"),
    )
    checkpointer = MemorySaver()

    agent: CompiledStateGraph = create_deep_agent(  # type: ignore[type-arg]
        model="openai:gpt-5.2",
        tools=[
            # 메모리
            save_memory,
            get_memory,
            list_memories,
            delete_memory,
            # 노트 (빠른 조회용 — 상세 작업은 note 서브에이전트)
            create_note,
            get_note,
            list_notes,
            search_notes,
            # 캘린더
            get_today_schedule,
            list_events,
            create_event,
            # 비용
            get_cost_summary,
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
    }

    return agent, config
