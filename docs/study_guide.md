# MPA 코드 공부 가이드

deepagents + LangChain으로 만든 개인 비서 코드베이스를 이해하기 위한 학습 가이드.

---

## 추천 읽기 순서

### Step 1 — 툴이 뭔지 이해 (가장 쉬운 것부터)

**`tools/memory.py`**
- 가장 단순한 툴. 그냥 Python 함수.
- docstring이 LLM의 "언제 이 툴을 쓸지" 판단 근거가 됨
- `save_memory(key, value)` → DB에 INSERT, `get_memory(key)` → SELECT
- 핵심 질문: "왜 LLM이 이 함수를 언제 호출할지 알 수 있을까?"

**`tools/changelog.py`**
- 툴이 툴을 import해서 호출하는 패턴 (append_changelog → sync_changelog_to_notion)
- 파일 I/O + 예외를 조용히 무시하는 이유 (Notion 미설정 환경 대응)

**`storage/db.py`**
- SQLite(로컬) / PostgreSQL(배포) 환경을 `PH` 변수 하나로 분기하는 방법
- `get_conn()` 컨텍스트 매니저 패턴

---

### Step 2 — 서브에이전트 구조 이해

**`agent/subagents/research.py`** ← 가장 단순한 서브에이전트
- `dict[str, object]` 형태로 정의: name / description / system_prompt / tools / model
- `description`이 오케스트레이터가 이 에이전트를 언제 호출할지 결정하는 유일한 기준
- 핵심 질문: "라우팅 코드가 어디 있지?" → 없음. LLM이 description을 읽고 판단.

**`agent/subagents/file.py`**
- 서브에이전트 system_prompt로 내장 툴(ls/glob) 사용을 금지하는 이유
- deepagents가 모든 에이전트에 built-in filesystem 툴을 제공하는데 이게 왜 문제인지

**`agent/subagents/github.py`**
- 서브에이전트 레벨에서 `interrupt_on` 설정하는 패턴
- 오케스트레이터 HITL과 어떻게 다른지

**`agent/subagents/code.py`** ← 가장 복잡한 서브에이전트
- `_make_sandbox_factory()` 클로저 패턴: 왜 클래스 안 쓰고 클로저?
- Modal Sandbox가 뭔지, 왜 클라우드 샌드박스에서 실행하는지
- `CompiledSubAgent`로 직접 wrapping하는 이유 (dict 방식과 차이)

---

### Step 3 — MCP 서버 이해

**`mcp_server/config.yaml`**
- `deny` vs `ignore` 차이: deny는 읽기 차단 / ignore는 목록 노출 차단
- `.env`, `*.key` 등 민감 파일 deny 패턴

**`mcp_server/main.py`**
- `_is_allowed()`: 경로가 허용 목록 안에 있는지 + deny 패턴 체크
- `_is_ignored_path()`: fnmatch로 glob 패턴 매칭
- fastmcp 툴 vs FastAPI REST 엔드포인트가 같은 파일에 공존하는 이유
- 핵심 질문: "왜 REST API를 따로 만들었나?" → 에이전트가 HTTP로 직접 호출 가능하게

**`utils/mcp_config.py`**
- config.yaml에서 허용 경로를 읽어 문자열로 변환하는 유틸
- 서브에이전트와 오케스트레이터 system_prompt에 동적으로 주입되는 방식

---

### Step 4 — 오케스트레이터 (핵심)

**`agent/orchestrator.py`**

읽을 때 순서:
1. `HITL_TOOLS` dict → 어떤 툴이 사용자 확인이 필요한지
2. `_get_checkpointer()` → MemorySaver vs AsyncPostgresSaver 분기 (단기 기억)
3. `_get_assistant_name()` → DB에서 장기 기억 꺼내는 방법
4. `create_orchestrator()` → `create_deep_agent()` 호출부. tools vs subagents 차이
5. `_SYSTEM_PROMPT_TEMPLATE` → 서브에이전트 라우팅 기준이 프롬프트로 명시됨

핵심 질문들:
- "tools와 subagents의 차이는?" → tools는 오케스트레이터가 직접 호출, subagents는 별도 LLM 에이전트
- "checkpointer가 뭐 하는 거야?" → LangGraph가 대화 상태를 여기에 저장. thread_id로 세션 구분
- "왜 gpt-5.2를 쓰나?" → 오케스트레이터는 복잡한 라우팅 판단이 필요해서 강력한 모델 사용

---

### Step 5 — 프론트엔드 (마지막)

**`frontend/app.py`**

읽을 때 순서:
1. `_TOOL_LABELS` dict → 툴 이름을 사용자 친화적 메시지로 변환
2. `_init_session()` → 세션마다 오케스트레이터 생성, LangGraph 상태 복원
3. `_stream_response()` → 에이전트 스트리밍 + 툴 호출 이벤트 처리
4. HITL 처리 부분 → interrupt_on 발동 시 어떻게 승인/취소하는지
5. `_export_chat()` → 대화 내보내기

핵심 질문:
- "왜 get_backend_loop()가 필요해?" → Streamlit은 동기, LangGraph는 async. 별도 스레드에 이벤트 루프를 띄워서 `asyncio.run_coroutine_threadsafe()`로 연결
- "HITL 승인 시 ainvoke(None)만 하면 되는데 왜 툴마다 다르게 처리해?" → deepagents built-in 툴(edit_file)은 프레임워크가 처리, 직접 등록한 툴(create_event)은 수동으로 ToolMessage 주입 필요

---

## 핵심 개념 요약

| 개념 | 한 줄 설명 | 코드 위치 |
|------|-----------|-----------|
| `create_deep_agent()` | LangGraph StateGraph를 자동 생성해주는 deepagents API | `orchestrator.py L200` |
| 서브에이전트 라우팅 | `description`을 LLM이 읽고 판단 — 라우팅 코드 없음 | `subagents/*.py` |
| 툴 docstring | LLM이 "언제/어떻게 호출할지" 결정하는 유일한 근거 | `tools/*.py` |
| 단기 기억 | LangGraph Checkpointer — thread_id로 대화 히스토리 유지 | `orchestrator.py L131` |
| 장기 기억 | `save_memory()` → DB — 대화가 끝나도 유지 | `tools/memory.py` |
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
