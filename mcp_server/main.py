"""로컬 MCP 서버 — fastmcp 기반 표준 MCP 프로토콜 + REST API 병행."""

import os
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastmcp import FastMCP

CONFIG_PATH = Path(__file__).parent / "config.yaml"

# ── 공통 유틸 ────────────────────────────────────────────────


def _load_config() -> dict[str, object]:
    return dict(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))


def _ignore_patterns(entry: dict[str, object]) -> list[str]:
    """config entry에서 ignore 패턴 목록을 반환한다."""
    raw = entry.get("ignore")
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if isinstance(p, str)]


def _is_ignored_path(path: Path, patterns: list[str]) -> bool:
    """경로의 any part가 ignore 패턴에 매칭되면 True."""
    import fnmatch

    for part in path.parts:
        if any(fnmatch.fnmatch(part, p) for p in patterns):
            return True
    return False


def _is_allowed(path: str, access: str = "read") -> bool:
    """경로가 허용 목록에 포함되는지 확인한다. deny 패턴에 해당하면 차단."""
    import fnmatch

    config = _load_config()
    resolved = Path(path).expanduser().resolve()
    allowed: list[object] = config.get("allowed_directories") or []  # type: ignore[assignment]
    for entry in allowed:
        if not isinstance(entry, dict):
            continue
        allowed_path = Path(str(entry.get("path", ""))).expanduser().resolve()
        if not str(resolved).startswith(str(allowed_path)):
            continue
        # deny 패턴 검사 — 파일명 기준
        raw_deny = entry.get("deny")
        deny_patterns: list[str] = (
            [str(p) for p in raw_deny if isinstance(p, str)] if isinstance(raw_deny, list) else []
        )
        filename = resolved.name
        if any(fnmatch.fnmatch(filename, pattern) for pattern in deny_patterns):
            return False
        if access == "read":
            return True
        if access == "write" and entry.get("access") == "read_write":
            return True
    return False


# ── fastmcp 서버 (표준 MCP 프로토콜) ────────────────────────

mcp = FastMCP("local-file-server")


@mcp.tool()
def read_local_file(path: str) -> str:
    """로컬 파일을 읽는다. 허용된 디렉토리 내 파일만 접근 가능. 코드/문서 분석에 사용."""
    if not _is_allowed(path):
        return f"접근 거부: '{path}'는 허용되지 않은 경로입니다."
    p = Path(path).expanduser()
    if not p.exists():
        return f"파일을 찾을 수 없습니다: {path}"
    if not p.is_file():
        return "파일이 아닙니다."
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"파일 읽기 실패: {e}"


@mcp.tool()
def list_local_files(directory: str = "~/projects") -> str:
    """로컬 디렉토리의 파일 목록을 반환한다. 허용된 디렉토리만 조회 가능."""
    config = _load_config()
    resolved = Path(directory).expanduser().resolve()
    allowed: list[object] = config.get("allowed_directories") or []  # type: ignore[assignment]
    patterns: list[str] = []
    for entry in allowed:
        if not isinstance(entry, dict):
            continue
        allowed_path = Path(str(entry.get("path", ""))).expanduser().resolve()
        if str(resolved).startswith(str(allowed_path)):
            patterns = _ignore_patterns(entry)
            break

    if not _is_allowed(directory):
        return f"접근 거부: '{directory}'는 허용되지 않은 경로입니다."
    d = Path(directory).expanduser()
    if not d.exists():
        return f"디렉토리를 찾을 수 없습니다: {directory}"
    if not d.is_dir():
        return "디렉토리가 아닙니다."
    files = sorted(
        str(f.relative_to(d)) for f in d.rglob("*") if f.is_file() and not _is_ignored_path(f.relative_to(d), patterns)
    )
    return "\n".join(files[:200]) if files else "파일이 없습니다."


# ── FastAPI REST (내부 에이전트용) ───────────────────────────

app = FastAPI(title="Local MCP Server")
security = HTTPBearer()


def _verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> HTTPAuthorizationCredentials:
    expected = os.environ.get("MCP_AUTH_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=500, detail="MCP_AUTH_TOKEN이 설정되지 않았습니다.")
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="인증 실패")
    return credentials


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/files/read")
async def rest_read_file(
    path: str = Query(...),
    _: HTTPAuthorizationCredentials = Depends(_verify_token),
) -> dict[str, str]:
    """허용된 경로의 파일 내용을 반환한다."""
    if not _is_allowed(path):
        raise HTTPException(status_code=403, detail=f"접근 거부: '{path}'")
    p = Path(path).expanduser()
    if not p.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="파일이 아닙니다.")
    try:
        return {"content": p.read_text(encoding="utf-8", errors="replace"), "path": str(p)}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"파일 읽기 실패: {e}") from e


@app.get("/files/list")
async def rest_list_files(
    path: str = Query(default="~/projects"),
    _: HTTPAuthorizationCredentials = Depends(_verify_token),
) -> dict[str, object]:
    """허용된 디렉토리의 파일 목록을 반환한다."""
    if not _is_allowed(path):
        raise HTTPException(status_code=403, detail=f"접근 거부: '{path}'")
    d = Path(path).expanduser()
    if not d.exists():
        raise HTTPException(status_code=404, detail="디렉토리를 찾을 수 없습니다.")
    if not d.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리가 아닙니다.")
    config = _load_config()
    resolved_d = d.resolve()
    allowed2: list[object] = config.get("allowed_directories") or []  # type: ignore[assignment]
    patterns2: list[str] = []
    for entry in allowed2:
        if not isinstance(entry, dict):
            continue
        allowed_path = Path(str(entry.get("path", ""))).expanduser().resolve()
        if str(resolved_d).startswith(str(allowed_path)):
            patterns2 = _ignore_patterns(entry)
            break
    files = [
        str(f.relative_to(d))
        for f in sorted(d.rglob("*"))
        if f.is_file() and not _is_ignored_path(f.relative_to(d), patterns2)
    ]
    return {"files": files[:200], "total": len(files), "directory": str(d)}


# MCP SSE 엔드포인트를 /mcp 경로에 마운트 (외부 클라이언트용)
app.mount("/mcp", mcp.http_app())


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("MCP_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
