"""CHANGELOG.md에 작업 내역을 자동으로 기록하는 툴."""

from datetime import date
from pathlib import Path

CHANGELOG_PATH = Path(__file__).parent.parent / "CHANGELOG.md"


def _today() -> str:
    return date.today().isoformat()


def append_changelog(summary: str, files: str | None = None) -> str:
    """CHANGELOG.md에 오늘 날짜로 작업 내역을 기록한다.

    코드 실행, 파일 수정/생성, 중요한 작업 완료 시 호출한다.
    같은 날 여러 번 호출하면 같은 날짜 섹션 아래에 누적된다.

    Args:
        summary: 작업 내용 요약 (예: "fibonacci 계산 스크립트 작성 및 실행")
        files: 변경된 파일 목록 (쉼표 구분, 예: "tools/sandbox.py, agent/orchestrator.py")
               파일 변경이 없으면 생략

    Returns:
        기록 완료 메시지
    """
    today = _today()
    entry_lines = [f"- {summary}"]
    if files:
        for f in files.split(","):
            f = f.strip()
            if f:
                entry_lines.append(f"  - `{f}`")
    entry = "\n".join(entry_lines)

    if not CHANGELOG_PATH.exists():
        CHANGELOG_PATH.write_text("# Changelog\n\n개인 비서가 수행한 작업 내역을 자동으로 기록합니다.\n\n")

    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    date_header = f"## {today}"

    if date_header in content:
        # 오늘 섹션에 항목 추가
        content = content.replace(
            date_header,
            f"{date_header}\n{entry}",
            1,
        )
    else:
        # 새 날짜 섹션 추가 (헤더 바로 뒤)
        header_end = content.find("\n\n", content.find("# Changelog")) + 2
        new_section = f"{date_header}\n{entry}\n\n"
        content = content[:header_end] + new_section + content[header_end:]

    CHANGELOG_PATH.write_text(content, encoding="utf-8")
    return f"CHANGELOG.md에 기록 완료: {summary}"


def read_changelog(limit: int = 30) -> str:
    """CHANGELOG.md의 최근 내역을 반환한다.

    Args:
        limit: 반환할 최대 줄 수 (기본 30줄)

    Returns:
        CHANGELOG.md 내용 (최근 limit줄)
    """
    if not CHANGELOG_PATH.exists():
        return "아직 기록된 작업 내역이 없습니다."

    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    recent = lines[:limit]
    result = "\n".join(recent)
    if len(lines) > limit:
        result += f"\n\n... (총 {len(lines)}줄 중 {limit}줄 표시)"
    return result
