"""노트 서브에이전트 — 메모, 논문 노트, 프롬프트 저장소 전담."""

from langchain.chat_models import init_chat_model

from tools.notes import (
    create_note,
    delete_note,
    get_note,
    list_notes,
    search_notes,
    update_note,
)

NOTE_SUBAGENT: dict[str, object] = {
    "name": "note",
    "description": (
        "메모 저장/조회/수정/삭제가 필요할 때 사용. 논문 노트 정리, 프롬프트 저장소, 실험 로그 기록 담당."
    ),
    "system_prompt": (
        "당신은 지식 관리 전문가입니다. "
        "사용자의 메모를 체계적으로 저장하고 검색합니다. "
        "논문 노트는 '논문' 태그, 프롬프트는 '프롬프트' 태그, "
        "실험 결과는 '실험' 태그를 붙여 분류하세요. "
        "검색 시 관련도 높은 결과를 우선 반환하세요."
    ),
    "tools": [create_note, get_note, list_notes, search_notes, update_note, delete_note],
    "model": init_chat_model("openai:gpt-4o-mini"),
}
