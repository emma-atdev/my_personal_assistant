# 코드 리뷰 Q&A

팀 리뷰 대비 예상 질문과 답변 모음.

---

## 아키텍처 전체 구조

### Orchestrator

| 항목 | 내용 |
|------|------|
| 모델 | gpt-5.2 |
| 역할 | 사용자 요청 수신 → 서브에이전트/툴에 위임 → 결과 반환 |
| 직접 실행 툴 | save_memory, get_memory, list_memories, delete_memory, get_today_schedule, list_events, create_event, get_cost_summary, create_notion_page, append_changelog, read_changelog |
| HITL 툴 | edit_file, write_file, create_event, create_notion_page |

### 서브에이전트 역할 & 툴 목록

| 서브에이전트 | 모델 | 역할 | 툴 |
|-------------|------|------|-----|
| research | gpt-4o-mini | 웹 검색, 논문 탐색 | search_web, fetch_hf_daily_papers, fetch_arxiv_papers |
| note | gpt-4o-mini | Notion 조회/수정, CHANGELOG 동기화 | search_notion, get_notion_page, append_notion_block, sync_changelog_to_notion |
| file | gpt-4o-mini | 로컬 파일 읽기, 디렉토리 탐색 | read_local_file, list_local_files |
| github | gpt-4o-mini | GitHub 이슈·PR 조회·생성·댓글 | list_my_issues, list_my_prs, get_issue, list_repo_issues, create_issue, comment_on_issue |
| cron | gpt-4o-mini | 브리핑·리포트 생성, Notion 저장 | create_notion_page, search_notion, get_cost_summary |
| code | gpt-4o | Python 코드 실행, 데이터 분석 | execute, write_file, edit_file, read_file (Modal Sandbox) |

---

## 비서 기능 & 질문 예시

| 기능 | 질문 예시 |
|------|---------|
| 웹 검색 | "RAG 최신 트렌드 알려줘", "LangGraph vs AutoGen 비교해줘" |
| 논문 탐색 | "HuggingFace 오늘 인기 논문 알려줘", "ArXiv에서 MoE 논문 찾아줘" |
| Notion | "Notion에서 RAG 페이지 찾아줘", "Notion에 주간 회고 페이지 만들어줘" |
| Google Calendar | "오늘 일정 알려줘", "다음 주 월요일 오후 3시에 미팅 잡아줘" |
| GitHub | "내 이슈 목록 알려줘", "내 PR 목록 보여줘", "할일 뭐 있어?" |
| Python 코드 실행 | "피보나치 수열 10개 계산해줘", "numpy로 행렬 SVD 분해 계산해줘" |
| 로컬 파일 분석 | "~/projects/my-app/main.py 읽어줘" (MCP 서버 실행 중일 때) |
| 장기 기억 | "내 주력 언어는 Python이야 기억해줘", "너 이름은 아리야" |
| API 비용 | "이번 달 API 비용 알려줘" |
| 자동 크론 | 매일 오전 10시 논문 브리핑, 매주 금요일 오후 5시 주간 리포트 |

---

## deepagents 프레임워크

**Q. deepagents가 뭐예요? LangGraph랑 다른가요?**
LangGraph 위에서 동작하는 추상화 레이어. `create_deep_agent()` 한 줄로 StateGraph 노드·엣지·체크포인터 설정을 자동 생성. LangGraph 직접 구현 시 필요한 ~100줄 보일러플레이트를 선언적 dict 구조로 대체.

**Q. create_deep_agent() 주요 파라미터가 뭐예요?**

| 파라미터 | 역할 |
|---------|------|
| `model` | 에이전트 LLM 지정 |
| `tools` | 직접 호출 가능한 툴 목록 |
| `subagents` | 위임 가능한 서브에이전트 (dict 또는 CompiledSubAgent) |
| `system_prompt` | 에이전트 역할/규칙 주입 |
| `checkpointer` | 단기 기억 (thread_id 기준 히스토리) |
| `interrupt_on` | HITL — 특정 툴 실행 직전 그래프 자동 중단 |
| `backend` | 툴 실행 백엔드 교체 (Modal Sandbox 등) |

**Q. 서브에이전트 라우팅 로직이 어디 있어요?**
없음. `description` 필드를 오케스트레이터 LLM이 읽고 어디로 보낼지 스스로 판단. `if "검색" in message` 같은 코드 분기 없음 — 프롬프트 엔지니어링이 라우팅.

**Q. deepagents tools / subagents / skills 차이가 뭐예요?**

| | tools | subagents | skills |
|-|-------|-----------|--------|
| 역할 | 에이전트가 호출하는 함수 | 전문 도메인 담당 독립 에이전트 | "어떻게 작업할지" 절차 지침 |
| 형태 | Python 함수 | 별도 LLM 인스턴스 | `SKILL.md` 마크다운 파일 |
| 로드 | 항상 시스템 프롬프트에 포함 | 오케스트레이터가 위임 시 실행 | 필요 시 에이전트가 직접 읽음 (Progressive Disclosure) |
| MPA 사용 | ✅ | ✅ | ❌ (system_prompt 하드코딩으로 대체) |

**Q. MPA에서 skills를 안 쓴 이유는?**
`_SYSTEM_PROMPT_TEMPLATE`에 라우팅 기준, 규칙, 페르소나를 직접 작성해서 별도 파일 관리가 불필요했음. skills를 도입하면 "논문 리서치 방법론", "주간 리포트 작성 방식" 같은 절차 지식을 파일로 분리하고 시스템 프롬프트를 경량화할 수 있음.

**Q. checkpointer가 두 종류인 이유는?**
로컬은 `MemorySaver`(인메모리, 재시작 시 초기화), 프로덕션은 `AsyncPostgresSaver`(Neon PostgreSQL, 영구 유지). `DATABASE_URL` 환경변수 유무로 자동 분기. dev/prod 환경에서 동일한 코드 사용.

초기화는 `async def init_checkpointer()`로 분리되어 FastAPI lifespan에서 서버 시작 시 한 번 호출됨. 이전의 threading 기반 초기화(`get_backend_loop()`)는 FastAPI가 natively async이므로 제거.

---

## OpenClaw × deepagents 기능 구현 현황

> OpenClaw: 자체 호스팅 AI 에이전트 게이트웨이. 멀티채널(WhatsApp·Telegram·Discord 등), Tools·Skills·Plugins 3-레이어 구조.

**Q. OpenClaw에서 영감받은 게 뭐예요?**
오케스트레이터가 요청을 받아 서브에이전트에 위임하는 패턴, 비서 이름 장기 기억, 자동 브리핑 크론잡.

**Q. MPA에서 구현한 것 / 못한 것이 뭐예요?**

| OpenClaw 기능 | deepagents 지원 | MPA | 비고 |
|---|---|---|---|
| Orchestrator-Subagent 라우팅 | ✅ `subagents` | ✅ | 핵심 구조 |
| 단기 기억 | ✅ `checkpointer` | ✅ MemorySaver / PostgresSaver | |
| 장기 기억 | ✅ `store`, `memory`(AGENTS.md) | ✅ save_memory → DB (커스텀) | AGENTS.md 미사용 |
| HITL | ✅ `interrupt_on` | ✅ 오케스트레이터 레벨만 | 서브에이전트 레벨 미동작 버그 |
| 코드 실행 샌드박스 | ✅ `backend` (Modal/Daytona/Deno) | ✅ Modal Sandbox | `backend` 파라미터로 교체 |
| 파일 접근 | ✅ `FilesystemBackend` | ✅ MCP 서버로 대체 | deepagents 내장 대신 MCP |
| 보안 (경로 제한) | allowlist / sandbox | ✅ MCP deny/ignore | |
| 크론잡 | 동적 등록/삭제 가능 | ✅ APScheduler (하드코딩) | 동적 등록 불가 — 개선점 |
| Skills (`SKILL.md`) | ✅ `skills` 파라미터 | ❌ system_prompt 하드코딩으로 대체 | |
| 대화 요약/압축 | ✅ `SummarizationMiddleware` | ✅ `create_deep_agent()` 기본 스택에 자동 포함 | |
| 멀티채널 | WhatsApp·Telegram·Discord 등 | ❌ Streamlit만 | 개선점 |
| 구조화된 출력 | ✅ `response_format` | ❌ | |
| 토큰 캐싱 | ✅ `AnthropicPromptCachingMiddleware` | ✅ `create_deep_agent()` 기본 스택에 자동 포함 | |
| 플러그인 마켓 | ClawHub | ❌ | |

**Q. OpenClaw 대비 MPA가 더 나은 점은?**
HITL(파괴적 작업 전 확인), MCP로 로컬 맥북 파일 접근, Modal Sandbox로 완전 격리된 코드 실행, LLM 비용 추적.

---

## 개선점

| 항목 | 현황 | 개선 방향 | 구현 방법 |
|------|------|----------|---------|
| 항목 | 현황 | 비고 |
|------|------|------|
| 대화 히스토리 압축 | ✅ `SummarizationMiddleware` — `create_deep_agent()` 기본 스택에 자동 포함 | 별도 설정 불필요 |
| 토큰 캐싱 | ✅ `AnthropicPromptCachingMiddleware` — `create_deep_agent()` 기본 스택에 자동 포함 | 별도 설정 불필요 |
| HITL 취소·중단 시 dangling tool call | ✅ `PatchToolCallsMiddleware` — `create_deep_agent()` 기본 스택에 자동 포함 | 별도 설정 불필요 |
| 오래된 대화 자동 정리 | ❌ `delete_conversation()`이 PostgreSQL 테이블 직접 삭제 (DB 종속) | `checkpointer.adelete_thread(thread_id)`로 교체 + APScheduler에 주기적 정리 크론 추가 |
| 시스템 프롬프트 경량화 | ❌ `_SYSTEM_PROMPT_TEMPLATE` 하드코딩 (~100줄) | `create_deep_agent(skills=["skills/research/", "skills/report/"])` |
| 동적 크론잡 | ❌ morning_briefing, weekly_report 하드코딩 | `schedule_task` / `cancel_task` 툴 → APScheduler `add_job()` / `remove_job()` 연동 |
| GitHub HITL | ❌ 서브에이전트 `interrupt_on` 미동작 | `HITL_TOOLS`에 추가 + github 서브에이전트에서 제거 |
| 멀티채널 | ❌ Streamlit 웹 UI만 | FastAPI `/webhook/telegram` 엔드포인트 추가. `thread_id="tg-{chat_id}"`로 채널별 대화 히스토리 분리 |
| 에이전트 답변 정형화 | ❌ 없음 — 응답 포맷이 매번 다름 | `create_deep_agent(response_format=MySchema)` — deepagents 지원하는데 미사용 |
| 툴 결과 검증 | ❌ 없음 — 오류 문자열을 LLM이 읽고 판단 | 개인 비서 용도라 LLM 자율 판단으로 충분하다고 판단 |
| 에이전트 평가 | ❌ 없음 | LangSmith 연동 |
| 프론트 UX | ❌ 기본 Streamlit UI | Streamlit custom components 또는 Next.js 전환 |

---

## backend/app.py

**Q. Streamlit이 에이전트를 직접 임포트하지 않는 이유는?**
리팩토링 후 Streamlit은 에이전트를 전혀 모름 — `httpx`로 FastAPI 엔드포인트만 호출. 에이전트 초기화·실행·checkpointer 관리 전부 백엔드에서. 이전에는 `create_orchestrator()`를 Streamlit에서 직접 호출하고 `asyncio`/`threading`으로 async 코드를 sync로 변환했음.

| 항목 | 기존 (앱 기반) | 현재 (API 기반) |
|------|--------------|----------------|
| 에이전트 실행 위치 | Streamlit 프로세스 내 | FastAPI 백엔드 |
| 스트리밍 | asyncio + Queue → sync | httpx SSE |
| HITL 처리 | `aget_state` / `aupdate_state` 직접 호출 | `POST /api/chat/resume` |

**Q. 새로 추가된 엔드포인트가 뭐예요?**

| 엔드포인트 | 역할 |
|-----------|------|
| `POST /api/chat` | 사용자 메시지 → SSE 스트리밍 (token·status·tool\_start·hitl·done 이벤트) |
| `POST /api/chat/resume` | HITL 확인/취소 후 에이전트 재개, 응답 반환 |
| `GET /api/chat/messages/{thread_id}` | 페이지 새로고침 시 대화 히스토리 복원 |

**Q. SSE 스트림에 어떤 이벤트가 있어요?**

| 이벤트 type | 의미 |
|------------|------|
| `token` | 응답 텍스트 청크 |
| `status` | "분석 중", "서브에이전트 실행 중" 등 상태 레이블 |
| `tool_start` / `tool_end` | 툴 호출 시작/완료 |
| `usage` | 토큰 사용량 |
| `hitl` | 사용자 확인 필요 (tool_name, tool_args, tool_call_id 포함) |
| `done` | 스트림 종료 |
| `error` | 오류 발생 |

**Q. HITL 흐름이 어떻게 돼요?**
```
① POST /api/chat 스트리밍 중 에이전트가 create_event 호출 시도
② LangGraph 그래프 일시정지 → SSE에 hitl 이벤트 전송
③ Streamlit이 hitl 이벤트 수신 → session_state에 저장 → 다이얼로그 표시
④ 사용자 승인 클릭 → POST /api/chat/resume {confirmed: true, tool_name, tool_args, tool_call_id}
   → 백엔드에서 툴 직접 실행 → ToolMessage 주입 → ainvoke(None) 재개
⑤ 사용자 취소 클릭 → POST /api/chat/resume {confirmed: false}
   → ToolMessage("취소됨") 주입 → ainvoke(None) 재개
```

`edit_file` / `write_file`은 deepagents가 직접 처리하므로 `ainvoke(None)`만 호출하면 내부적으로 실행됨. `create_event` / `create_notion_page`는 백엔드가 직접 실행 후 ToolMessage 주입.

---

## agent/orchestrator.py

**Q. 캘린더는 왜 서브에이전트로 안 만들었어요?**
툴이 3개뿐(get_today_schedule, list_events, create_event)이라 별도 LLM 불필요. 서브에이전트 만들면 오케스트레이터 → 서브에이전트 LLM 호출이 한 번 더 생겨 비용/지연 증가. 복잡한 판단이 필요 없는 단순 API 호출은 직접 툴로.

**Q. interrupt_on은 커스텀 구현인가요?**
deepagents/LangGraph 프레임워크 기능. 선언만 하면 해당 툴 호출 직전에 그래프 실행을 자동으로 멈춤. 미들웨어처럼 툴 노드 진입 전에 끼어드는 구조. 항상 툴 실행 전에 막아서 취소해도 부작용 없음.

**Q. HITL이 두 레이어인 이유는?**
오케스트레이터 레벨(create_event, create_notion_page)과 서브에이전트 레벨(create_issue, comment_on_issue) — 책임 분리. 서브에이전트 툴은 오케스트레이터 interrupt_on으로 못 막음. 각 레벨에서 독립적으로 설정.

**Q. recursion_limit=50은 왜요?**
LangGraph 기본값 25. 서브에이전트 구조에서 오케스트레이터 → 서브에이전트 → 툴 → 서브에이전트 → 오케스트레이터 순회가 많아져 기본값으로는 복잡한 요청에서 RecursionError 발생. 50으로 올림. 50도 넉넉하진 않아서 매우 복잡한 요청은 여전히 걸릴 수 있음.

**Q. create_notion_page가 note 서브에이전트 아닌 오케스트레이터에 있는 이유?**
HITL 적용하려면 오케스트레이터 레벨 tools에 있어야 함. 서브에이전트 안에 있으면 interrupt_on이 걸리지 않아서 사용자 확인 없이 바로 생성됨.

---

## tools/changelog.py

**Q. changelog는 언제 작성되나요?**
에이전트가 작업을 완료한 직후 오케스트레이터가 `append_changelog`를 직접 호출. system_prompt에 호출 기준이 명시되어 있어서 LLM이 판단:

| 호출 기준 | 예시 |
|----------|------|
| 코드 작성 또는 실행 | Modal Sandbox에서 스크립트 실행 |
| 파일 생성 또는 수정 | write_file, edit_file 완료 후 |
| 장문 결과물 생성 | 논문 브리핑, 주간 리포트 |
| 메모/캘린더/이슈·PR 생성 | save_memory, create_event, create_issue |
| Notion 페이지 생성/수정 | create_notion_page, append_notion_block |

**Q. changelog 기록 구조가 어떻게 되나요?**
`CHANGELOG.md`에 날짜별로 누적. 같은 날 여러 번 호출하면 같은 날짜 섹션 아래에 항목 추가:

```markdown
## 2026-03-25
- fibonacci 계산 스크립트 작성 및 실행
- Notion에 주간 회고 페이지 생성
  - `tools/changelog.py`
```

`append_changelog` 완료 시 `sync_changelog_to_notion()` 자동 호출 → Notion 페이지에도 동기화. `NOTION_CHANGELOG_PAGE_ID` 미설정 시 조용히 무시.

**Q. read_changelog가 30줄 제한인데 프론트에서도 표기돼요?**
read_changelog 결과는 LLM을 거쳐 사용자에게 전달됨. "총 X줄 중 30줄 표시" 메시지가 그대로 나올 수도 있고 LLM이 생략할 수도 있어서 보장 안 됨. 프론트에서 직접 렌더링하지 않는 구조상 한계.

**Q. append_changelog 안에서 왜 Notion 동기화를 직접 호출해요?**
Notion 동기화를 에이전트가 별도로 기억하지 않아도 되게끔 의도적으로 묶은 것. changelog 기록과 Notion 동기화를 항상 함께 일어나는 하나의 작업으로 취급. NOTION_CHANGELOG_PAGE_ID 미설정 시 조용히 무시해서 Notion 없는 환경에서도 동작.

---

## tools/github_tools.py

**Q. create_issue / comment_on_issue는 HITL이 어디서 걸려요?**
현재 github 서브에이전트 레벨에서 `interrupt_on` 설정되어 있으나 **실제로 동작하지 않음**. 서브에이전트 내부 인터럽트가 오케스트레이터로 전파될 때 HITL로 인식되지 않고 툴 오류(`Interrupt` 예외)로 처리됨. 오케스트레이터 레벨 `interrupt_on`(create_event 등)만 정상 동작 확인됨.

**→ 개선 필요**: `create_issue`, `comment_on_issue`를 오케스트레이터 레벨 tools로 올리고 `HITL_TOOLS`에 추가해야 실제 사용자 확인이 걸림.

---

## agent/subagents/code.py

**Q. deepagents execute 툴 쓰면 되는데 왜 Modal Sandbox를 써요?**
deepagents 기본 execute는 서버(Fly.io) 로컬 환경에서 실행됨. 내 맥북 패키지가 없고, 잘못된 코드가 서버에 영향을 줄 수 있음. Modal Sandbox는 완전 격리된 클라우드 컨테이너 — pip install 자유롭고 호스트에 영향 없음.

**Q. backend 파라미터가 뭐예요?**
deepagents의 코드 실행 백엔드를 교체하는 파라미터. 기본값 대신 `ModalSandbox`를 주입하면 execute/write_file/read_file이 모두 Modal 컨테이너 안에서 동작. E2B, Docker 등으로도 교체 가능.

**Q. _make_sandbox_factory() 클로저 패턴은 왜 써요?**
Modal Sandbox는 생성 비용이 큼(최초 30~60초). 클로저로 `_sandbox` 상태를 유지해서 살아있으면 재사용, 만료됐을 때만 재생성. 클래스 대신 클로저를 쓴 이유는 상태를 최소화하기 위함.

**Q. dict 방식 서브에이전트 아닌 CompiledSubAgent를 쓴 이유는?**
dict 방식은 표준 툴 목록만 받아서 `backend` 파라미터를 전달할 수 없음. `create_deep_agent()` 결과를 직접 `CompiledSubAgent`로 감싸야 커스텀 backend 주입 가능.

---

## agent/subagents/file.py

**Q. deepagents read_file 내장 툴 쓰면 되는데 왜 MCP 써요?**
deepagents 내장 `read_file`은 서버(Fly.io) 파일시스템을 접근함. 사용자의 로컬 맥북 파일(`~/projects/my-app/main.py`)은 서버에 없음. MCP 서버 + ngrok 터널로 로컬 파일을 외부에 안전하게 노출해서 에이전트가 HTTP로 접근.

**Q. MCP가 뭐예요?**
Model Context Protocol. AI가 외부 도구(파일시스템, DB 등)에 접근하는 표준 프로토콜. 이 프로젝트에서는 로컬 MCP 서버(port 8002)를 ngrok 고정 도메인으로 터널링해서 Fly.io 에이전트가 로컬 파일을 읽을 수 있게 함.

**Q. ngrok이 뭐예요?**
로컬 서버에 인터넷 주소를 붙여주는 터널 서비스. 공유기 뒤 사설망에 있는 맥북은 공인 IP가 없어서 Fly.io가 직접 접근 불가능. ngrok을 실행하면 `https://xxx.ngrok-free.app` 같은 공인 도메인이 발급되고, 이 도메인으로 들어오는 요청을 `localhost:8002`로 전달해줌.

```
맥북 (사설망)                      인터넷
┌──────────────────┐             ┌──────────────────────────┐
│  MCP 서버         │◄────────────►│  xxx.ngrok-free.app      │
│  localhost:8002  │   터널       │  (공인 도메인 · HTTPS)    │
└──────────────────┘             └──────────────────────────┘
                                          ▲
                                          │ HTTP 요청
                                   Fly.io file 서브에이전트
```

- **고정 도메인**: ngrok 유료/무료 플랜에서 고정 도메인 설정 가능 → 재시작해도 URL 유지 → `MCP_SERVER_URL` 한 번만 설정
- **보안**: ngrok은 HTTPS 전용 + `MCP_AUTH_TOKEN` 헤더 검증 + `config.yaml` 경로 제한으로 이중화

**Q. file 서브에이전트 system_prompt에서 내장 툴을 금지한 이유는?**
deepagents가 모든 에이전트에 `ls`, `glob`, `read_file` 등을 자동 제공하는데, 이걸 쓰면 서버 파일시스템을 봄. 실수로 사용하지 않도록 system_prompt에 명시적으로 금지.

**Q. MCP 서버로 파일 쓰기도 가능한가요?**
현재는 읽기 전용. `mcp_server/main.py`에 `/files/read`와 `/files/list` 엔드포인트만 구현되어 있음. 쓰기 엔드포인트(`/files/write`)가 없어서 에이전트가 요청해도 물리적으로 불가능.

`config.yaml`에 `access: "read_write"` 설정과 `_is_allowed(path, access="write")` 로직은 이미 있어서 엔드포인트만 추가하면 쓰기 활성화 가능. 단, 로컬 파일 수정은 되돌리기 어려우므로 HITL 적용 필수.

**Q. BackendProtocol을 구현해서 MCP 대신 쓸 수 있나요?**
가능하지만 용도가 다름. `BackendProtocol`은 코드 실행 백엔드(execute/write_file/read_file)를 교체하는 인터페이스 — 파일 서브에이전트의 "로컬 파일 읽기 툴"과는 역할이 분리됨. BackendProtocol로 구현하면 file 서브에이전트 없이 code 서브에이전트 안에서 로컬 파일도 읽을 수 있지만, 코드 실행과 파일 접근 책임이 섞여서 현재 구조보다 복잡해짐.

---

## 프론트엔드 — Streamlit 선택 이유

**Q. Streamlit에서 에이전트를 어떻게 호출해요?**
`httpx`로 FastAPI 엔드포인트를 동기 호출. `_run_events(thread_id, user_input)`가 `POST /api/chat`에 SSE 스트리밍 요청을 보내고, 줄 단위로 파싱해서 Generator로 반환. `asyncio`/`threading` 없이 순수 동기 코드.

```python
def _run_events(thread_id, user_input):
    with httpx.Client(timeout=None) as client:
        with client.stream("POST", f"{BACKEND_URL}/api/chat", ...) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    yield json.loads(line[6:])
```

`BACKEND_URL`은 `.env`에서 로드 — 로컬은 `http://localhost:8000`, 배포 시 `https://mpa-jm.fly.dev`.

**Q. 왜 Telegram 같은 봇 대신 웹 UI를 만들었어요?**
텔레그램 봇은 채팅창 하나만 있는 구조라 아래 기능을 넣기 어려움:

| 필요한 기능 | 텔레그램 봇 | Streamlit 웹 |
|------------|------------|-------------|
| 추천 질문 버튼 | 제한적 (InlineKeyboard만) | ✅ 자유롭게 배치 |
| 아침 브리핑 / 주간 리포트 전용 뷰 | ❌ 일반 메시지로만 | ✅ 별도 탭/컴포넌트 |
| HITL 승인/취소 버튼 | 제한적 | ✅ st.button으로 구현 |
| API 비용, 상태 정보 사이드바 | ❌ | ✅ 사이드바 |
| WebSocket 실시간 알림 렌더링 | ❌ | ✅ |

웹 UI는 추가 기능(사이드바 메뉴, 추천 질문, 브리핑 탭 등)을 자유롭게 붙일 수 있어서 Streamlit 선택.

**Q. 그럼 나중에 텔레그램 추가도 가능해요?**
가능함. 개선점에도 기재됨. 대화 채널만 다르고 에이전트 코어는 동일하게 재사용 가능:

```
Telegram Bot → FastAPI /webhook/telegram 엔드포인트
  → message 파싱 → orchestrator.invoke()
  → 응답 → bot.send_message()
```

HITL(승인/취소)은 텔레그램 InlineKeyboard로 대체하면 됨. 단, 브리핑 탭이나 사이드바 같은 웹 전용 UI는 텔레그램에서 제공 불가 — 채널에 따라 기능 일부 제한 감수해야 함.

---

## storage/db.py

**Q. SQLite 실제로 써요?**
초기 설계에서 로컬 폴백용으로 넣었음. 지금은 로컬도 Neon PostgreSQL 씀. .env.example에서 DATABASE_URL 주석 처리해두어서 SQLite 폴백 가능한 상태로는 유지 중.
