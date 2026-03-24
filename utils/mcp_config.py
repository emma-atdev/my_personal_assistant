"""MCP 서버 config.yaml 읽기 유틸."""

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "mcp_server" / "config.yaml"


def allowed_dirs_str() -> str:
    """config.yaml에서 허용 디렉토리 목록을 읽어 문자열로 반환한다."""
    try:
        config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        entries = config.get("allowed_directories", [])
        paths = [e["path"] for e in entries if isinstance(e, dict) and "path" in e]
        return ", ".join(paths) if paths else "~/my_personal_assistant"
    except Exception:  # noqa: BLE001
        return "~/my_personal_assistant"
