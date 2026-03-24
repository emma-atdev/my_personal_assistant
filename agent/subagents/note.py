"""노트 서브에이전트 — Notion 페이지 관리 전담."""

from langchain.chat_models import init_chat_model

from tools.notion_tools import (
    append_notion_block,
    create_notion_page,
    get_notion_page,
    search_notion,
    sync_changelog_to_notion,
)

NOTE_SUBAGENT: dict[str, object] = {
    "name": "note",
    "description": ("메모 저장·조회가 필요할 때 사용. Notion 페이지 검색·조회·생성, CHANGELOG Notion 동기화도 담당."),
    "system_prompt": (
        "당신은 지식 관리 전문가입니다.\n"
        "모든 메모와 노트는 Notion에 저장합니다.\n\n"
        "활용 기준:\n"
        "- Notion 검색 → search_notion\n"
        "- Notion 페이지 읽기 → get_notion_page\n"
        "- Notion 페이지 생성 → create_notion_page\n"
        "- Notion 페이지에 내용 추가 → append_notion_block\n"
        "- CHANGELOG → Notion 동기화 → sync_changelog_to_notion\n"
    ),
    "tools": [
        search_notion,
        get_notion_page,
        create_notion_page,
        append_notion_block,
        sync_changelog_to_notion,
    ],
    "model": init_chat_model("openai:gpt-4o-mini"),
}
