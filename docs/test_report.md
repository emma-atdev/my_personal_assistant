# 테스트 현황 보고서

마지막 업데이트: 2026-03-20

---

## 검증 도구 개요

| 도구 | 역할 | 한계 |
|------|------|------|
| `mypy` | 타입 힌트 검사, 타입 불일치 감지 | 런타임 로직 버그는 잡지 못함 |
| `ruff` | 코드 스타일, import 정렬, 불필요한 코드 제거 | 로직 오류는 잡지 못함 |
| `pytest` | 함수 단위 동작 검증, DB 읽기/쓰기 확인 | LLM 비결정적 동작, UI, 시간 의존 로직은 어려움 |

---

## 1. mypy 결과

**결과**: `Success: no issues found in 30 source files`

### 수정한 오류 목록

| 파일 | 오류 내용 | 수정 방법 |
|------|----------|----------|
| `utils/logger.py` | `on_llm_start` 시그니처가 부모 클래스와 불일치 (`prompts: list[str]` vs `messages: list[list[BaseMessage]]`) | `on_chat_model_start`으로 메서드명 변경 (Chat 모델용 올바른 메서드) |
| `utils/logger.py` | `getattr(gen, "message", {}).content` — `dict`에 `.content` 없음 | `getattr`로 단계적으로 분리해 None 방어 처리 |
| `storage/db.py` | SQLite 브랜치에서 `conn` 변수 타입이 `_PgConnWrapper`로 추론됨 | SQLite 브랜치 변수명을 `sqlite_conn`으로 분리 |
| `mcp_server/main.py` | `type: ignore[union-attr]` 주석이 실제 오류 코드(`attr-defined`)와 불일치 | 변수로 추출 후 올바른 타입 처리 |

---

## 2. ruff 결과

**결과**: `All checks passed!`

### 수정한 오류 목록

| 파일 | 오류 코드 | 내용 | 수정 방법 |
|------|----------|------|----------|
| `agent/orchestrator.py` | `I001` | import 블록 정렬 불일치 | 서드파티 → 로컬 순서로 재정렬 |
| `agent/orchestrator.py` | `E501` | 줄 길이 초과 (134 > 110) | 시스템 프롬프트 문자열 줄바꿈 |
| `frontend/app.py` | `UP043` | `Generator[str, None, None]` — 불필요한 기본 타입 인수 | `Generator[str]`로 축약 |
| `storage/db.py` | `UP035` | `from typing import Generator` 구버전 import | `from collections.abc import Generator`로 변경 |
| `storage/db.py` | `UP043` | `Generator[Any, None, None]` 불필요한 기본 타입 인수 | `Generator[Any]`로 축약 |

---

## 3. pytest 결과

**실행일**: 2026-03-20
**환경**: 임시 SQLite DB (각 테스트마다 독립된 DB, 실제 Neon DB 미사용)
**결과**: **23 passed / 0 failed (0.18s)**

### 픽스처 구조

`tests/conftest.py`의 `use_test_db` 픽스처가 모든 테스트에 자동 적용됩니다.

```
각 테스트 실행 시
  └→ monkeypatch로 DATABASE_URL 제거 (SQLite 강제)
  └→ tmp_path로 테스트 전용 임시 DB 파일 생성
  └→ tools.memory / tools.notes / tools.cost_tracker의 get_conn을 임시 DB로 교체
  └→ 테스트 종료 후 임시 DB 자동 삭제
```

> **포인트**: `tools/memory.py` 등은 `from storage.db import get_conn`으로 직접 import하기 때문에 `storage.db.get_conn`만 패치해서는 안 되고, 각 툴 모듈의 `get_conn`도 별도로 패치해야 합니다.

### 테스트 결과 상세

```
tests/test_api.py::test_health                          PASSED
tests/test_api.py::test_get_notes_empty                 PASSED
tests/test_api.py::test_search_notes_empty              PASSED
tests/test_api.py::test_get_costs_empty                 PASSED
tests/test_api.py::test_get_latest_briefing_empty       PASSED
tests/test_cost_tracker.py::test_cost_summary_empty     PASSED
tests/test_cost_tracker.py::test_log_and_get_cost_summary PASSED
tests/test_cost_tracker.py::test_cost_calculation       PASSED
tests/test_cost_tracker.py::test_multiple_models        PASSED
tests/test_memory.py::test_save_and_get_memory          PASSED
tests/test_memory.py::test_get_missing_memory           PASSED
tests/test_memory.py::test_overwrite_memory             PASSED
tests/test_memory.py::test_list_memories_empty          PASSED
tests/test_memory.py::test_list_memories                PASSED
tests/test_memory.py::test_delete_memory                PASSED
tests/test_notes.py::test_create_and_get_note           PASSED
tests/test_notes.py::test_get_missing_note              PASSED
tests/test_notes.py::test_list_notes_empty              PASSED
tests/test_notes.py::test_list_notes                    PASSED
tests/test_notes.py::test_search_notes                  PASSED
tests/test_notes.py::test_search_notes_no_result        PASSED
tests/test_notes.py::test_update_note                   PASSED
tests/test_notes.py::test_delete_note                   PASSED
```

### 테스트 커버리지 상세

#### `tools/memory.py`
| 테스트 | 검증 내용 |
|--------|----------|
| `test_save_and_get_memory` | 저장 후 동일 값 조회 |
| `test_get_missing_memory` | 없는 키 조회 시 안내 메시지 반환 |
| `test_overwrite_memory` | 동일 키 재저장 시 값 덮어쓰기 |
| `test_list_memories_empty` | 빈 DB에서 목록 조회 |
| `test_list_memories` | 여러 기억 저장 후 목록 확인 |
| `test_delete_memory` | 삭제 후 조회 시 없음 확인 |

#### `tools/notes.py`
| 테스트 | 검증 내용 |
|--------|----------|
| `test_create_and_get_note` | 생성 후 ID로 조회, 제목/내용 확인 |
| `test_get_missing_note` | 없는 ID 조회 시 안내 메시지 반환 |
| `test_list_notes_empty` | 빈 DB에서 목록 조회 |
| `test_list_notes` | 여러 메모 생성 후 목록 확인 |
| `test_search_notes` | 키워드로 제목/내용 검색 |
| `test_search_notes_no_result` | 없는 키워드 검색 시 안내 메시지 반환 |
| `test_update_note` | 내용 수정 후 변경 확인 |
| `test_delete_note` | 삭제 후 조회 시 없음 확인 |

#### `tools/cost_tracker.py`
| 테스트 | 검증 내용 |
|--------|----------|
| `test_cost_summary_empty` | 기록 없을 때 안내 메시지 반환 |
| `test_log_and_get_cost_summary` | 비용 기록 후 요약에 모델명/금액 포함 확인 |
| `test_cost_calculation` | gpt-4o-mini 1000+500 토큰 = $0.00045 계산 검증 |
| `test_multiple_models` | 여러 모델 기록 후 요약에 모두 포함 확인 |

#### `backend/app.py`
| 테스트 | 검증 내용 |
|--------|----------|
| `test_health` | `/api/health` 200 응답 및 `{"status": "ok"}` 반환 |
| `test_get_notes_empty` | `/api/notes` 200 응답, `notes` 키 포함 확인 |
| `test_search_notes_empty` | `/api/notes/search` 200 응답, `result` 키 포함 확인 |
| `test_get_costs_empty` | `/api/costs` 200 응답, `summary` 키 포함 확인 |
| `test_get_latest_briefing_empty` | `/api/briefing/latest` 200 응답, `briefing` 키 포함 확인 |

---

## 4. 미완료 테스트 및 구현 방법

### MCP 서버 엔드포인트 (`/files/read`, `/files/list`)

**현재 문제**: ngrok 터널과 실제 파일 경로에 의존해 자동화 테스트 어려움

**구현 방법**:
```python
# httpx.TestClient로 직접 테스트, 허용 경로를 tmp_path로 교체
from fastapi.testclient import TestClient
import mcp_server.main as mcp_app

def test_list_files(tmp_path, monkeypatch):
    # config.yaml의 allowed_directories를 tmp_path로 교체
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token")
    # tmp_path에 테스트 파일 생성 후 요청
    (tmp_path / "test.txt").write_text("hello")
    # config를 mock해서 tmp_path 허용
    ...
```

---

### `tools/local_file.py`

**현재 문제**: MCP 서버가 실행 중이어야 하고 `MCP_SERVER_URL`이 필요

**구현 방법**:
```python
# httpx를 mock해서 MCP 서버 응답을 가짜로 대체
from unittest.mock import patch, MagicMock

def test_read_local_file(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8002")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"content": "파일 내용"}
    mock_response.raise_for_status = lambda: None

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        result = read_local_file("~/my_personal_assistant/README.md")
        assert "파일 내용" in result
```

---

### 크론잡 (브리핑/리포트 생성)

**현재 문제**: APScheduler 시간 의존적, LLM 호출 포함

**구현 방법**:
```python
# LLM 호출을 mock하고 스케줄러 트리거만 직접 실행
from unittest.mock import AsyncMock, patch
from cron.scheduler import morning_briefing

async def test_morning_briefing(monkeypatch):
    with patch("cron.scheduler.create_orchestrator") as mock_orch:
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": [...]}
        mock_orch.return_value = (mock_agent, {})
        await morning_briefing()
        mock_agent.ainvoke.assert_called_once()
```

---

### WebSocket 브로드캐스트

**현재 문제**: 비동기 연결 테스트 구성 필요

**구현 방법**:
```python
# pytest-asyncio + httpx AsyncClient로 WebSocket 테스트
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app

@pytest.mark.asyncio
async def test_broadcast():
    async with AsyncClient(transport=ASGITransport(app=app)) as client:
        response = await client.post("/api/broadcast", json={"type": "test", "message": "hello"})
        assert response.status_code == 200
        assert response.json() == {"status": "sent"}
```

---

### 에이전트 동작 (툴 선택)

**현재 문제**: LLM 응답 비결정적, 실행마다 비용 발생

**구현 방법 (E2E 테스트로 별도 관리)**:
- LLM mock 라이브러리(`langchain-community`의 `FakeListChatModel`) 사용
- 또는 실제 LLM으로 테스트하되 CI에서는 스킵 (`@pytest.mark.skipif`)
```python
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="API 키 없으면 스킵")
async def test_agent_uses_search_tool():
    agent, config = create_orchestrator("test")
    result = await agent.ainvoke({"messages": [HumanMessage("최신 AI 뉴스 알려줘")]}, config)
    # research 서브에이전트가 호출됐는지 확인
    ...
```

---

### Streamlit UI

**현재 문제**: Python 서버라 브라우저 레벨 테스트 필요

**구현 방법**:
- Playwright + pytest-playwright로 E2E 테스트
```bash
uv add --dev pytest-playwright
playwright install chromium

# 테스트 예시
async def test_chat_ui(page):
    await page.goto("http://localhost:8001")
    await page.fill("[data-testid='stChatInput']", "안녕")
    await page.press("[data-testid='stChatInput']", "Enter")
    await page.wait_for_selector(".stChatMessage")
```
