"""GitHub 서브에이전트 — Issues, PRs, 레포 관리 전담."""

from auth.langchain_chatgpt import get_model
from tools.github_tools import (
    comment_on_issue,
    create_issue,
    get_issue,
    list_my_issues,
    list_my_prs,
    list_repo_issues,
)

GITHUB_SUBAGENT: dict[str, object] = {
    "name": "github",
    "description": (
        "GitHub 관련 작업이 필요할 때 사용. "
        "담당 이슈 조회, PR 목록, 이슈 생성·댓글, 레포 이슈 탐색 담당. "
        "할일 목록 확인 시에도 활용."
    ),
    "system_prompt": (
        "당신은 GitHub 전문 에이전트입니다.\n"
        "GITHUB_TOKEN으로 인증된 사용자의 이슈와 PR을 조회하고 관리합니다.\n\n"
        "활용 기준:\n"
        "- '내 이슈', '할일' → list_my_issues\n"
        "- '내 PR', '리뷰 대기' → list_my_prs\n"
        "- 특정 레포 이슈 → list_repo_issues\n"
        "- 이슈 상세 → get_issue\n"
        "- 이슈 생성 → create_issue (HITL 필요)\n"
        "- 댓글 작성 → comment_on_issue (HITL 필요)\n\n"
        "주의:\n"
        "- 툴은 토큰에서 사용자명을 자동으로 가져오므로 사용자에게 사용자명·인증 정보를 요청하지 말 것\n"
        "- 결과가 없으면 없다고 간단히 답할 것 — 추가 정보 요청 금지\n\n"
        "결과는 한국어로 요약해서 전달하세요."
    ),
    "tools": [
        list_my_issues,
        list_my_prs,
        get_issue,
        list_repo_issues,
        create_issue,
        comment_on_issue,
    ],
    "model": get_model(pkce_model="gpt-5.1-codex-mini", openai_fallback="openai:gpt-4o-mini"),
    "interrupt_on": {
        "create_issue": True,
        "comment_on_issue": True,
    },
}
