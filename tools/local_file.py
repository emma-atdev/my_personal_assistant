"""로컬 파일 접근 툴 — 로컬 MCP 서버를 통해 허용된 경로에 접근한다."""

import os

import httpx


def _headers() -> dict[str, str]:
    token = os.environ.get("MCP_AUTH_TOKEN", "")
    return {"Authorization": f"Bearer {token}"}


def _base_url() -> str:
    return os.environ.get("MCP_SERVER_URL", "http://localhost:8002")


def read_local_file(file_path: str) -> str:
    """로컬 파일을 읽는다. 허용된 디렉토리 내 파일만 접근 가능. 코드/문서 분석에 사용."""
    mcp_url = os.environ.get("MCP_SERVER_URL")
    if not mcp_url:
        return "MCP_SERVER_URL이 설정되지 않았습니다. 로컬 MCP 서버를 먼저 실행하세요."
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{_base_url()}/files/read",
                params={"path": file_path},
                headers=_headers(),
            )
            resp.raise_for_status()
            return str(resp.json().get("content", ""))
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            return f"접근 거부: '{file_path}'는 허용되지 않은 경로입니다."
        if e.response.status_code == 404:
            return f"파일을 찾을 수 없습니다: {file_path}"
        return f"파일 읽기 실패: {e}"
    except httpx.HTTPError as e:
        return f"MCP 서버 연결 실패: {e}"


def list_local_files(directory: str = "~/projects") -> str:
    """로컬 디렉토리의 파일 목록을 가져온다. 허용된 디렉토리만 조회 가능."""
    mcp_url = os.environ.get("MCP_SERVER_URL")
    if not mcp_url:
        return "MCP_SERVER_URL이 설정되지 않았습니다. 로컬 MCP 서버를 먼저 실행하세요."
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{_base_url()}/files/list",
                params={"path": directory},
                headers=_headers(),
            )
            resp.raise_for_status()
            files: list[str] = resp.json().get("files", [])
            return "\n".join(files) if files else "파일이 없습니다."
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            return f"접근 거부: '{directory}'는 허용되지 않은 경로입니다."
        return f"목록 조회 실패: {e}"
    except httpx.HTTPError as e:
        return f"MCP 서버 연결 실패: {e}"
