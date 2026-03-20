"""tools/notes.py 단위 테스트."""

from tools.notes import create_note, delete_note, get_note, list_notes, search_notes, update_note


def test_create_and_get_note() -> None:
    result = create_note("테스트 제목", "테스트 내용", "태그1")
    assert "저장 완료" in result

    note_id = int(result.split("ID: ")[1].split(")")[0])
    note = get_note(note_id)
    assert "테스트 제목" in note
    assert "테스트 내용" in note


def test_get_missing_note() -> None:
    result = get_note(99999)
    assert "찾을 수 없습니다" in result


def test_list_notes_empty() -> None:
    result = list_notes()
    assert "없습니다" in result


def test_list_notes() -> None:
    create_note("제목1", "내용1")
    create_note("제목2", "내용2")
    result = list_notes()
    assert "제목1" in result
    assert "제목2" in result


def test_search_notes() -> None:
    create_note("LangGraph 정리", "LangGraph는 그래프 기반 에이전트 프레임워크", "AI")
    result = search_notes("LangGraph")
    assert "LangGraph" in result


def test_search_notes_no_result() -> None:
    result = search_notes("존재하지않는키워드xyz")
    assert "검색 결과가 없습니다" in result


def test_update_note() -> None:
    create_note("수정 테스트", "원본 내용")
    note_id_str = create_note("수정 테스트2", "원본 내용2")
    note_id = int(note_id_str.split("ID: ")[1].split(")")[0])

    update_note(note_id, "수정된 내용")
    note = get_note(note_id)
    assert "수정된 내용" in note


def test_delete_note() -> None:
    result = create_note("삭제 테스트", "삭제할 내용")
    note_id = int(result.split("ID: ")[1].split(")")[0])

    delete_note(note_id)
    result = get_note(note_id)
    assert "찾을 수 없습니다" in result
