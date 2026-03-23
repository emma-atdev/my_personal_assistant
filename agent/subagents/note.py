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
from tools.notion_tools import (
    append_notion_block,
    create_notion_page,
    get_notion_page,
    search_notion,
    sync_changelog_to_notion,
)

NOTE_SUBAGENT: dict[str, object] = {
    "name": "note",
    "description": (
        "메모 저장/조회/수정/삭제가 필요할 때 사용. "
        "Notion 페이지 검색·조회·생성, CHANGELOG Notion 동기화도 담당."
    ),
    "system_prompt": (
        "당신은 지식 관리 전문가입니다.\n"
        "로컬 메모(create_note 등)와 Notion(search_notion 등) 두 가지를 관리합니다.\n\n"
        "활용 기준:\n"
        "- 로컬 메모 저장/조회 → create_note, search_notes 등\n"
        "- Notion 검색 → search_notion\n"
        "- Notion 페이지 읽기 → get_notion_page\n"
        "- Notion 페이지 생성 → create_notion_page\n"
        "- Notion 페이지에 내용 추가 → append_notion_block\n"
        "- CHANGELOG → Notion 동기화 → sync_changelog_to_notion\n\n"
        "논문 노트는 '논문' 태그, 프롬프트는 '프롬프트' 태그로 분류하세요."
    ),
    "tools": [
        create_note,
        get_note,
        list_notes,
        search_notes,
        update_note,
        delete_note,
        search_notion,
        get_notion_page,
        create_notion_page,
        append_notion_block,
        sync_changelog_to_notion,
    ],
    "model": init_chat_model("openai:gpt-4o-mini"),
}
