"""크론 서브에이전트 — 브리핑과 리포트 생성 전담."""

from langchain.chat_models import init_chat_model

from tools.cost_tracker import get_cost_summary
from tools.notes import create_note, search_notes

CRON_SUBAGENT: dict[str, object] = {
    "name": "cron",
    "description": (
        "정기 브리핑 생성, 주간 리포트 작성, 비용 리포트가 필요할 때 사용. "
        "수집된 논문과 뉴스를 요약해 메모로 저장하는 작업 담당."
    ),
    "system_prompt": (
        "당신은 보고서 작성 전문가입니다. "
        "수집된 정보를 간결하고 명확하게 요약합니다. "
        "브리핑은 핵심만 추려 읽기 쉽게 마크다운으로 작성하고, "
        "논문은 제목, 링크, 한 줄 요약 형식으로 정리하세요."
    ),
    "tools": [create_note, search_notes, get_cost_summary],
    "model": init_chat_model("openai:gpt-4o-mini"),
}
