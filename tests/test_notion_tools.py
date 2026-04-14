"""tools/notion_tools.py 마크다운 파싱 테스트 — Notion API 호출 없이 블록 변환만 검증."""

from tools.notion_tools import (
    _bullet,
    _heading,
    _paragraph,
    _parse_rich_text,
)

# ── _parse_rich_text: 인라인 포맷팅 ─────────────────────────


class TestParseRichText:
    """인라인 마크다운 → Notion rich_text 배열 변환 테스트."""

    def test_plain_text(self) -> None:
        result = _parse_rich_text("안녕하세요")
        assert len(result) == 1
        assert result[0]["text"]["content"] == "안녕하세요"
        assert result[0].get("annotations", {}).get("bold") is not True

    def test_bold(self) -> None:
        result = _parse_rich_text("이것은 **볼드** 텍스트")
        texts = [r["text"]["content"] for r in result]
        assert "볼드" in texts
        bold_part = next(r for r in result if r["text"]["content"] == "볼드")
        assert bold_part["annotations"]["bold"] is True

    def test_italic(self) -> None:
        result = _parse_rich_text("이것은 *이탤릭* 텍스트")
        texts = [r["text"]["content"] for r in result]
        assert "이탤릭" in texts
        italic_part = next(r for r in result if r["text"]["content"] == "이탤릭")
        assert italic_part["annotations"]["italic"] is True

    def test_inline_code(self) -> None:
        result = _parse_rich_text("함수 `foo()` 호출")
        texts = [r["text"]["content"] for r in result]
        assert "foo()" in texts
        code_part = next(r for r in result if r["text"]["content"] == "foo()")
        assert code_part["annotations"]["code"] is True

    def test_link(self) -> None:
        result = _parse_rich_text("여기 [구글](https://google.com) 링크")
        texts = [r["text"]["content"] for r in result]
        assert "구글" in texts
        link_part = next(r for r in result if r["text"]["content"] == "구글")
        assert link_part["text"]["link"]["url"] == "https://google.com"

    def test_mixed_inline(self) -> None:
        result = _parse_rich_text("**볼드**와 *이탤릭* 혼합")
        texts = [r["text"]["content"] for r in result]
        assert "볼드" in texts
        assert "이탤릭" in texts

    def test_empty_string(self) -> None:
        result = _parse_rich_text("")
        assert result == []


# ── 블록 헬퍼 ───────────────────────────────────────────────


class TestBlockHelpers:
    """기존 블록 헬퍼가 _parse_rich_text를 사용하는지 확인."""

    def test_heading_with_bold(self) -> None:
        block = _heading("**중요** 제목", 1)
        rich = block["heading_1"]["rich_text"]
        texts = [r["text"]["content"] for r in rich]
        assert "중요" in texts

    def test_bullet_with_link(self) -> None:
        block = _bullet("[링크](https://example.com) 항목")
        rich = block["bulleted_list_item"]["rich_text"]
        link_part = next(
            (r for r in rich if r["text"]["content"] == "링크"),
            None,
        )
        assert link_part is not None
        assert link_part["text"]["link"]["url"] == "https://example.com"

    def test_paragraph_plain(self) -> None:
        block = _paragraph("일반 텍스트")
        rich = block["paragraph"]["rich_text"]
        assert rich[0]["text"]["content"] == "일반 텍스트"


# ── _append_markdown: 블록 타입 파싱 ────────────────────────


class TestAppendMarkdownBlocks:
    """_append_markdown가 마크다운을 올바른 Notion 블록으로 변환하는지 검증.

    실제 API 호출 대신 _markdown_to_blocks 헬퍼를 직접 테스트한다.
    """

    def test_numbered_list(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        blocks = _markdown_to_blocks("1. 첫 번째\n2. 두 번째\n3. 세 번째")
        num_blocks = [b for b in blocks if b["type"] == "numbered_list_item"]
        assert len(num_blocks) == 3

    def test_code_block(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        md = "```python\nprint('hello')\n```"
        blocks = _markdown_to_blocks(md)
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 1
        code = code_blocks[0]["code"]
        assert code["language"] == "python"
        rich = code["rich_text"]
        assert rich[0]["text"]["content"] == "print('hello')"

    def test_code_block_no_lang(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        md = "```\nsome code\n```"
        blocks = _markdown_to_blocks(md)
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 1
        assert code_blocks[0]["code"]["language"] == "plain text"

    def test_todo_unchecked(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        blocks = _markdown_to_blocks("- [ ] 할 일")
        todo_blocks = [b for b in blocks if b["type"] == "to_do"]
        assert len(todo_blocks) == 1
        assert todo_blocks[0]["to_do"]["checked"] is False

    def test_todo_checked(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        blocks = _markdown_to_blocks("- [x] 완료된 일")
        todo_blocks = [b for b in blocks if b["type"] == "to_do"]
        assert len(todo_blocks) == 1
        assert todo_blocks[0]["to_do"]["checked"] is True

    def test_quote(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        blocks = _markdown_to_blocks("> 인용문입니다")
        quote_blocks = [b for b in blocks if b["type"] == "quote"]
        assert len(quote_blocks) == 1

    def test_callout(self) -> None:
        from tools.notion_tools import _markdown_to_blocks

        blocks = _markdown_to_blocks("> [!NOTE]\n> 참고 사항입니다")
        callout_blocks = [b for b in blocks if b["type"] == "callout"]
        assert len(callout_blocks) == 1

    def test_mixed_content(self) -> None:
        """여러 블록 타입이 섞인 마크다운."""
        from tools.notion_tools import _markdown_to_blocks

        md = """# 제목

일반 문단

- 불릿 1
- 불릿 2

1. 번호 1
2. 번호 2

```python
x = 1
```

> 인용문

- [ ] 할 일
- [x] 완료"""
        blocks = _markdown_to_blocks(md)
        types = [b["type"] for b in blocks]
        assert "heading_1" in types
        assert "paragraph" in types
        assert "bulleted_list_item" in types
        assert "numbered_list_item" in types
        assert "code" in types
        assert "quote" in types
        assert "to_do" in types
