"""Notion API 툴 — 페이지 조회, 생성, 검색, CHANGELOG 동기화."""

import os
import re
from functools import lru_cache
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError


@lru_cache(maxsize=1)
def _client() -> Client:
    """Notion 클라이언트를 반환한다."""
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise RuntimeError("NOTION_API_KEY 환경변수가 설정되지 않았습니다.")
    return Client(auth=token)


def _blocks_to_text(blocks: list[Any]) -> str:
    """Notion 블록 목록을 텍스트로 변환한다."""
    lines: list[str] = []
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype, {})
        rich_texts = data.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_texts)

        if btype == "heading_1":
            lines.append(f"# {text}")
        elif btype == "heading_2":
            lines.append(f"## {text}")
        elif btype == "heading_3":
            lines.append(f"### {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "to_do":
            checked = data.get("checked", False)
            lines.append(f"[{'x' if checked else ' '}] {text}")
        elif btype == "code":
            lang = data.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif btype == "divider":
            lines.append("---")
        elif text:
            lines.append(text)

    return "\n".join(lines)


def search_notion(query: str, limit: int = 10) -> str:
    """Notion 워크스페이스에서 페이지를 검색한다.

    Args:
        query: 검색어
        limit: 최대 반환 개수, 기본값 10

    Returns:
        검색된 페이지 목록 (제목, URL)
    """
    try:
        resp: Any = _client().search(query=query, page_size=limit)
        results = resp.get("results", [])
        if not results:
            return f"'{query}' 검색 결과 없음"

        lines: list[str] = []
        for item in results:
            obj_type = item.get("object", "")
            url = item.get("url", "")

            if obj_type == "page":
                props = item.get("properties", {})
                title_prop = props.get("title") or props.get("Name") or {}
                rich_texts = title_prop.get("title", []) or title_prop.get("rich_text", [])
                title = "".join(rt.get("plain_text", "") for rt in rich_texts) or "(제목 없음)"
                lines.append(f"📄 {title}\n   {url}")

        return "\n\n".join(lines) if lines else f"'{query}' 검색 결과 없음"
    except APIResponseError as e:
        return f"Notion API 오류: {e}"


def get_notion_page(page_id: str) -> str:
    """Notion 페이지 내용을 조회한다.

    Args:
        page_id: 페이지 ID (URL 마지막 32자리 또는 하이픈 포함 UUID)

    Returns:
        페이지 제목과 본문 내용
    """
    try:
        page = _client().pages.retrieve(page_id=page_id)
        props = page.get("properties", {})  # type: ignore[union-attr]
        title_prop = props.get("title") or props.get("Name") or {}
        rich_texts = title_prop.get("title", []) or title_prop.get("rich_text", [])
        title = "".join(rt.get("plain_text", "") for rt in rich_texts) or "(제목 없음)"

        blocks_resp = _client().blocks.children.list(block_id=page_id)
        blocks = blocks_resp.get("results", [])  # type: ignore[union-attr]
        content = _blocks_to_text(blocks)

        return f"# {title}\n\n{content}" if content else f"# {title}\n\n(내용 없음)"
    except APIResponseError as e:
        return f"Notion API 오류: {e}"


def create_notion_page(title: str, content: str, parent_page_id: str | None = None) -> str:
    """Notion에 새 페이지를 생성한다.

    Args:
        title: 페이지 제목
        content: 페이지 본문 (마크다운 형식)
        parent_page_id: 상위 페이지 ID (없으면 NOTION_DEFAULT_PARENT_PAGE_ID 사용)

    Returns:
        생성된 페이지 URL
    """
    try:
        resolved_parent = parent_page_id or os.getenv("NOTION_DEFAULT_PARENT_PAGE_ID")
        parent: dict[str, Any] = (
            {"type": "page_id", "page_id": resolved_parent}
            if resolved_parent
            else {"type": "workspace", "workspace": True}
        )

        page = _client().pages.create(
            parent=parent,
            properties={"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        )
        page_id = page["id"]  # type: ignore[index]
        url = page["url"]  # type: ignore[index]

        # 본문 추가 (첫 줄이 제목과 같은 # 헤더면 스킵)
        if content:
            lines = content.splitlines(keepends=True)
            body = "".join(lines[1:]).lstrip() if lines and lines[0].strip() in (f"# {title}", "#") else content
            _append_markdown(page_id, body)

        return f"페이지 생성 완료: {url}"
    except APIResponseError as e:
        return f"Notion API 오류: {e}"


def append_notion_block(page_id: str, content: str) -> str:
    """Notion 페이지 하단에 내용을 추가한다.

    Args:
        page_id: 페이지 ID
        content: 추가할 내용 (마크다운 형식)

    Returns:
        추가 완료 메시지
    """
    try:
        _append_markdown(page_id, content)
        return "Notion 페이지에 내용 추가 완료"
    except APIResponseError as e:
        return f"Notion API 오류: {e}"


def sync_changelog_to_notion() -> str:
    """CHANGELOG.md 내용을 Notion 페이지에 동기화한다.

    NOTION_CHANGELOG_PAGE_ID 환경변수로 지정된 페이지에 기록합니다.

    Returns:
        동기화 완료 메시지 또는 오류
    """
    from tools.changelog import CHANGELOG_PATH

    page_id = os.getenv("NOTION_CHANGELOG_PAGE_ID")
    if not page_id:
        return "NOTION_CHANGELOG_PAGE_ID 환경변수가 설정되지 않았습니다."

    if not CHANGELOG_PATH.exists():
        return "CHANGELOG.md 파일이 없습니다."

    try:
        content = CHANGELOG_PATH.read_text(encoding="utf-8")

        # 페이지 제목 업데이트
        _update_page_title(page_id, "Changelog")

        # 기존 블록 삭제 후 새로 작성 (# Changelog 헤더 제외)
        blocks_resp = _client().blocks.children.list(block_id=page_id)
        for block in blocks_resp.get("results", []):  # type: ignore[union-attr]
            _client().blocks.delete(block_id=block["id"])

        lines = content.splitlines(keepends=True)
        body = "".join(lines[1:]).lstrip() if lines and lines[0].startswith("# ") else content
        _append_markdown(page_id, body)
        page = _client().pages.retrieve(page_id=page_id)
        url = page.get("url", "")  # type: ignore[union-attr]
        return f"CHANGELOG.md → Notion 동기화 완료: {url}"
    except APIResponseError as e:
        return f"Notion API 오류: {e}"


def _update_page_title(page_id: str, title: str) -> None:
    """Notion 페이지 제목을 업데이트한다."""
    _client().pages.update(
        page_id=page_id,
        properties={"title": {"title": [{"type": "text", "text": {"content": title}}]}},
    )


_CALLOUT_ICONS: dict[str, str] = {
    "NOTE": "ℹ️",
    "TIP": "💡",
    "IMPORTANT": "❗",
    "WARNING": "⚠️",
    "CAUTION": "🔴",
}

_NUMBERED_RE = re.compile(r"^\d+\.\s+")


def _markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """마크다운 텍스트를 Notion 블록 리스트로 변환한다."""
    blocks: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # 코드 블록 (```)
        if line.startswith("```"):
            lang = line[3:].strip() or "plain text"
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(_code_block("\n".join(code_lines), lang))
            i += 1  # ``` 닫는 줄 건너뛰기
            continue

        # callout (> [!TYPE])
        if line.startswith("> [!") and "]" in line:
            tag = line.split("]")[0].replace("> [!", "").strip().upper()
            icon = _CALLOUT_ICONS.get(tag, "ℹ️")
            callout_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i].startswith("> "):
                callout_lines.append(lines[i][2:])
                i += 1
            blocks.append(_callout("\n".join(callout_lines), icon))
            continue

        # 인용 (>)
        if line.startswith("> "):
            blocks.append(_quote(line[2:]))
            i += 1
            continue

        # 헤딩
        if line.startswith("### "):
            blocks.append(_heading(line[4:], 3))
        elif line.startswith("## "):
            blocks.append(_heading(line[3:], 2))
        elif line.startswith("# "):
            blocks.append(_heading(line[2:], 1))
        # 체크박스
        elif line.startswith("- [x] ") or line.startswith("- [X] "):
            blocks.append(_todo(line[6:], checked=True))
        elif line.startswith("- [ ] "):
            blocks.append(_todo(line[6:], checked=False))
        # 불릿 리스트
        elif line.startswith("- "):
            blocks.append(_bullet(line[2:]))
        # 번호 리스트
        elif _NUMBERED_RE.match(line):
            text = _NUMBERED_RE.sub("", line)
            blocks.append(_numbered(text))
        # 구분선
        elif line.startswith("---"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        # 일반 텍스트 / 빈 줄
        elif line.strip():
            blocks.append(_paragraph(line))
        else:
            blocks.append(_paragraph(""))

        i += 1

    return blocks


def _append_markdown(page_id: str, markdown: str) -> None:
    """마크다운 텍스트를 Notion 블록으로 변환해 페이지에 추가한다."""
    blocks = _markdown_to_blocks(markdown)

    # Notion API는 한 번에 최대 100개 블록 — 배치로 분할
    for start in range(0, len(blocks), 99):
        batch = blocks[start : start + 99]
        _client().blocks.children.append(block_id=page_id, children=batch)


_INLINE_PATTERN = re.compile(
    r"(?P<bold>\*\*(?P<bold_text>.+?)\*\*)"
    r"|(?P<code>`(?P<code_text>[^`]+)`)"
    r"|(?P<link>\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^)]+)\))"
    r"|(?P<italic>\*(?P<italic_text>[^*]+)\*)"
)


def _parse_rich_text(text: str) -> list[dict[str, Any]]:
    """인라인 마크다운을 Notion rich_text 배열로 변환한다.

    지원: **볼드**, *이탤릭*, `코드`, [텍스트](URL)
    """
    if not text:
        return []

    result: list[dict[str, Any]] = []
    pos = 0

    for m in _INLINE_PATTERN.finditer(text):
        # 매치 전 plain text
        if m.start() > pos:
            plain = text[pos : m.start()]
            if plain:
                result.append({"type": "text", "text": {"content": plain[:2000]}})

        if m.group("bold"):
            result.append(
                {
                    "type": "text",
                    "text": {"content": m.group("bold_text")[:2000]},
                    "annotations": {"bold": True},
                }
            )
        elif m.group("code"):
            result.append(
                {
                    "type": "text",
                    "text": {"content": m.group("code_text")[:2000]},
                    "annotations": {"code": True},
                }
            )
        elif m.group("link"):
            result.append(
                {
                    "type": "text",
                    "text": {
                        "content": m.group("link_text")[:2000],
                        "link": {"url": m.group("link_url")},
                    },
                }
            )
        elif m.group("italic"):
            result.append(
                {
                    "type": "text",
                    "text": {"content": m.group("italic_text")[:2000]},
                    "annotations": {"italic": True},
                }
            )

        pos = m.end()

    # 남은 plain text
    if pos < len(text):
        result.append({"type": "text", "text": {"content": text[pos:][:2000]}})

    return result if result else [{"type": "text", "text": {"content": text[:2000]}}]


def _heading(text: str, level: int) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _parse_rich_text(text)}}


def _bullet(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _parse_rich_text(text)},
    }


def _numbered(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": _parse_rich_text(text)},
    }


def _todo(text: str, *, checked: bool = False) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {"rich_text": _parse_rich_text(text), "checked": checked},
    }


def _quote(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": _parse_rich_text(text)},
    }


def _callout(text: str, icon: str = "ℹ️") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _parse_rich_text(text),
            "icon": {"type": "emoji", "emoji": icon},
        },
    }


def _code_block(code: str, language: str = "plain text") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": code[:2000]}}],
            "language": language,
        },
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _parse_rich_text(text) if text else []},
    }
