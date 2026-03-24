# MPA 코드 공부 가이드

deepagents + LangChain으로 만든 개인 비서 코드베이스를 이해하기 위한 학습 가이드.

---

## 전체 읽기 순서 한 장 요약

```
PART 1 — 전체 구조
  storage/db.py → utils/mcp_config.py → utils/logger.py

PART 2 — 툴
  tools/memory.py → tools/search.py → tools/papers.py
  → tools/changelog.py → tools/notion_tools.py → tools/github_tools.py
  → tools/calendar_tools.py → tools/cost_tracker.py
  → tools/local_file.py → tools/conversations.py

PART 3 — 에이전트
  subagents/research.py → subagents/note.py → subagents/file.py
  → subagents/github.py → subagents/cron.py → subagents/code.py
  → agent/orchestrator.py  ← 핵심

PART 4 — MCP 서버
  mcp_server/config.yaml → mcp_server/main.py

PART 5 — 백엔드
  cron/scheduler.py → cron/jobs/morning_briefing.py
  → cron/jobs/weekly_report.py → backend/app.py

PART 6 — 프론트엔드
  frontend/app.py  ← 마지막
```

---

## PART 1 — 전체 구조

### `storage/db.py`
- `DATABASE_URL` 있으면 PostgreSQL, 없으면 SQLite — 환경 분기를 변수 하나(`PH`, `IS_PG`)로 처리
- `_PgConnWrapper` — psycopg2를 SQLite처럼 `con.execute()`로 쓰게 감싼 어댑터 패턴
- `@contextmanager get_conn()` — with문으로 커넥션 열고/닫고/롤백을 자동 처리
- **핵심 질문**: "왜 SQLite랑 PostgreSQL을 같이 지원하나?" → 로컬은 파일 DB, 배포는 Neon

### `utils/mcp_config.py`
- config.yaml에서 허용 경로 읽어서 문자열로 반환
- 짧지만 orchestrator와 file 서브에이전트 양쪽에 주입되는 흐름 파악

### `utils/logger.py`
- 에이전트 실행 중 어떤 이벤트를 로깅하는지만 훑어보기

---

## PART 2 — 툴 (tools/)

### `tools/memory.py`
- 가장 단순한 툴. `save_memory` / `get_memory` / `list_memories` / `delete_memory`
- **포인트**: docstring이 LLM의 툴 선택 근거. 함수 시그니처 + docstring만 보고 LLM이 판단
- `PH` 플레이스홀더로 SQLite/PostgreSQL 분기 (db.py에서 배운 패턴이 여기 적용)

### `tools/search.py`
- Tavily API 호출. 외부 API를 툴로 감싸는 가장 단순한 패턴

### `tools/papers.py`
- ArXiv / HuggingFace / Papers with Code 세 곳에서 논문 수집
- **포인트**: 툴 하나가 여러 출처를 추상화하는 방법

### `tools/changelog.py`
- `append_changelog` 내부에서 `sync_changelog_to_notion`을 직접 import해서 호출
- **포인트**: 툴이 툴을 호출하는 패턴, 예외를 조용히 무시하는 이유 (Notion 미설정 환경 대응)

### `tools/notion_tools.py`
- Notion API 4종: `search_notion` / `get_notion_page` / `create_notion_page` / `append_notion_block`
- **포인트**: `create_notion_page`에서 `NOTION_DEFAULT_PARENT_PAGE_ID` fallback 처리

### `tools/github_tools.py`
- GitHub REST API 호출. `GITHUB_TOKEN`에서 사용자명 자동 추출
- **포인트**: 인증 정보를 사용자에게 묻지 않고 토큰에서 뽑아쓰는 구조

### `tools/calendar_tools.py`
- Google Calendar API. OAuth 토큰 갱신 처리

### `tools/cost_tracker.py`
- LLM 비용을 DB에 로깅하고 월별 집계

### `tools/local_file.py`
- MCP 서버에 HTTP 요청 보내는 클라이언트 툴
- **포인트**: 실제 파일 읽기는 여기서 안 함. MCP 서버에 위임. `MCP_SERVER_URL` + `MCP_AUTH_TOKEN` 사용

### `tools/conversations.py`
- 대화 세션(thread_id) 관리. 제목 저장/조회

---

## PART 3 — 에이전트 (agent/)

### `agent/subagents/research.py`
- 가장 단순한 서브에이전트. `dict`로 선언하는 구조 파악
- **포인트**: `description`이 라우팅 기준. `system_prompt`로 이 에이전트의 행동 제약

### `agent/subagents/note.py`
- `create_notion_page`가 없는 이유 → HITL 때문에 오케스트레이터로 올린 설계 결정

### `agent/subagents/file.py`
- system_prompt에서 내장 툴(`ls`, `glob`) 금지하는 이유
- **포인트**: deepagents가 모든 에이전트에 filesystem 툴을 자동 제공하는데, 여기선 쓰면 안 됨

### `agent/subagents/github.py`
- 서브에이전트 레벨 `interrupt_on` 패턴
- **포인트**: 오케스트레이터 HITL과 다른 점

### `agent/subagents/cron.py`
- 브리핑/리포트 생성 전용

### `agent/subagents/code.py`
- 가장 복잡. `_make_sandbox_factory()` 클로저 패턴
- **포인트**: 왜 `dict` 방식이 아니라 `CompiledSubAgent`로 직접 wrapping했는지, 클로저로 샌드박스 재사용하는 이유

### `agent/orchestrator.py` ← 핵심
읽는 순서:
1. `HITL_TOOLS` — 어떤 툴이 차단되는지
2. `_get_checkpointer()` — 단기 기억 설정
3. `_get_assistant_name()` — 장기 기억 꺼내기
4. `create_orchestrator()` — `create_deep_agent()` 호출부, tools vs subagents 차이
5. `_SYSTEM_PROMPT_TEMPLATE` — 서브에이전트 라우팅 기준이 여기에

---

## PART 4 — MCP 서버

### `mcp_server/config.yaml`
- deny vs ignore 차이 먼저 파악
- deny: 파일 읽기 자체를 차단 / ignore: 목록에서만 숨김

### `mcp_server/main.py`
- `_is_allowed()` → `_is_ignored_path()` 읽기
- fastmcp 툴(`@mcp.tool()`)과 FastAPI REST 엔드포인트가 같은 파일에 있는 이유

---

## PART 5 — 백엔드

### `cron/scheduler.py`
- APScheduler 설정. 언제 어떤 job이 실행되는지

### `cron/jobs/morning_briefing.py` → `cron/jobs/weekly_report.py`
- 크론잡이 에이전트를 어떻게 호출하는지

### `backend/app.py`
- FastAPI 엔드포인트 목록 훑기
- WebSocket 브로드캐스트 구조
- lifespan으로 scheduler 시작/종료 관리

---

## PART 6 — 프론트엔드

### `frontend/app.py` ← 마지막
읽는 순서:
1. `_TOOL_LABELS` — 툴 이름 → 사람 친화적 메시지 매핑
2. `_init_session()` — 오케스트레이터 생성 + LangGraph 상태 복원
3. `_stream_response()` — 에이전트 스트리밍 + 툴 이벤트 처리
4. HITL 승인/취소 처리 부분
5. `_export_chat()`

**포인트**: `get_backend_loop()` + `asyncio.run_coroutine_threadsafe()` — Streamlit(동기)에서 async 에이전트 실행하는 핵심 패턴

---

## 핵심 개념 요약

| 개념 | 한 줄 설명 | 코드 위치 |
|------|-----------|-----------|
| `create_deep_agent()` | LangGraph StateGraph를 자동 생성해주는 deepagents API | `orchestrator.py L200` |
| 서브에이전트 라우팅 | `description`을 LLM이 읽고 판단 — 라우팅 코드 없음 | `subagents/*.py` |
| 툴 docstring | LLM이 "언제/어떻게 호출할지" 결정하는 유일한 근거 | `tools/*.py` |
| 단기 기억 | LangGraph Checkpointer — thread_id로 대화 히스토리 유지 | `orchestrator.py L131` |
| 장기 기억 | `save_memory()` → DB — 대화가 끊겨도 유지 | `tools/memory.py` |
| HITL | `interrupt_on`으로 특정 툴 전 LangGraph 실행 일시정지 | `orchestrator.py L99` |
| MCP | AI가 로컬 파일에 접근하기 위한 표준 프로토콜 + ngrok 터널 | `mcp_server/` |
| 동기-비동기 | Streamlit(동기)에서 LangGraph(async) 실행하는 스레드 패턴 | `orchestrator.py L111` |

---

## 팀 리뷰에서 나올 법한 질문

1. **"라우팅 로직이 어디 있어요?"** → 없음. LLM이 description 읽고 판단. 프롬프트 엔지니어링의 실제 사례.
2. **"왜 서브에이전트마다 모델이 달라요?"** → 오케스트레이터는 복잡한 판단(gpt-5.2), 서브에이전트는 단순 실행(gpt-4o-mini). 비용 최적화.
3. **"HITL이 두 레이어인 이유?"** → 오케스트레이터 레벨(Notion/캘린더)과 서브에이전트 레벨(GitHub) — 책임 분리.
4. **"왜 클로저 패턴 썼어요?"** (`code.py`) → Modal Sandbox 재사용. 클래스보다 상태를 최소화.
5. **"MCP가 뭐예요?"** → Model Context Protocol. AI가 외부 도구에 접근하는 표준화된 방식.
6. **"ngrok은 왜 써요?"** → Streamlit Cloud/Fly.io에서 로컬 맥북 파일에 접근하려면 터널 필요.
