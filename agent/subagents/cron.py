"""크론 서브에이전트 — 브리핑과 리포트 생성 전담."""

from agent.subagents import get_subagent_model
from templates.notion_format import (
    BRIEFING_INSTRUCTIONS,
    CHANGELOG_INSTRUCTIONS,
    MARKDOWN_GUIDE,
    REPORT_INSTRUCTIONS,
)
from tools.cost_tracker import get_cost_summary
from tools.notion_tools import create_notion_page, search_notion

_CRON_SYSTEM_PROMPT = f"""\
당신은 보고서 작성 전문가입니다.
수집된 정보를 간결하고 명확하게 요약합니다.
결과물은 create_notion_page로 Notion에 저장하세요.

{MARKDOWN_GUIDE}

--- 아침 브리핑 ---
{BRIEFING_INSTRUCTIONS}

--- 주간 리포트 ---
{REPORT_INSTRUCTIONS}

--- Changelog ---
{CHANGELOG_INSTRUCTIONS}
"""

CRON_SUBAGENT: dict[str, object] = {
    "name": "cron",
    "description": (
        "정기 브리핑 생성, 주간 리포트 작성, 비용 리포트가 필요할 때 사용. "
        "수집된 논문과 뉴스를 요약해 Notion에 저장하는 작업 담당."
    ),
    "system_prompt": _CRON_SYSTEM_PROMPT,
    "tools": [create_notion_page, search_notion, get_cost_summary],
    "model": get_subagent_model(),
}
