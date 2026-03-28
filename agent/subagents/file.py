"""파일 서브에이전트 — 로컬 MCP 서버를 통한 파일 접근 전담."""

from auth.langchain_chatgpt import get_model
from tools.local_file import list_local_files, read_local_file
from utils.mcp_config import allowed_dirs_str as _allowed_dirs_str

_allowed = _allowed_dirs_str()

FILE_SUBAGENT: dict[str, object] = {
    "name": "file",
    "description": (
        "로컬 파일 읽기나 디렉토리 탐색이 필요할 때 사용. "
        "코드 분석, 문서 요약, 로컬 프로젝트 파일 접근 담당. "
        "MCP 서버가 실행 중일 때만 동작."
    ),
    "system_prompt": (
        "당신은 파일 분석 전문가입니다.\n"
        f"접근 가능한 경로: {_allowed}\n"
        "위 경로 외(/, /home, /workspace, /root 등)는 허용되지 않습니다.\n\n"
        "필수 규칙:\n"
        "- 파일 목록 조회는 반드시 list_local_files 툴만 사용\n"
        "- 파일 읽기는 반드시 read_local_file 툴만 사용\n"
        "- ls, glob, read_file 등 내장 툴 사용 금지 (로컬 파일시스템에 연결되지 않음)\n\n"
        "코드 파일은 구조와 핵심 로직을 요약하고, 문서 파일은 핵심 내용을 추출해 정리하세요."
    ),
    "tools": [read_local_file, list_local_files],
    "model": get_model(pkce_model="gpt-5.1-codex-mini", openai_fallback="openai:gpt-4o-mini"),
}
