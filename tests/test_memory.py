"""tools/memory.py 단위 테스트."""

from tools.memory import delete_memory, get_memory, list_memories, save_memory


def test_save_and_get_memory() -> None:
    save_memory("name", "짱구")
    result = get_memory("name")
    assert result == "짱구"


def test_get_missing_memory() -> None:
    result = get_memory("nonexistent_key")
    assert "기억이 없습니다" in result


def test_overwrite_memory() -> None:
    save_memory("name", "짱구")
    save_memory("name", "철수")
    result = get_memory("name")
    assert result == "철수"


def test_list_memories_empty() -> None:
    result = list_memories()
    assert "없습니다" in result


def test_list_memories() -> None:
    save_memory("key1", "value1")
    save_memory("key2", "value2")
    result = list_memories()
    assert "key1" in result
    assert "key2" in result


def test_delete_memory() -> None:
    save_memory("to_delete", "value")
    delete_memory("to_delete")
    result = get_memory("to_delete")
    assert "기억이 없습니다" in result
