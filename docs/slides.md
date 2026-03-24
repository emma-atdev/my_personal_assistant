# My Personal Assistant — 발표 슬라이드 초안

---

## Slide 1 — 프로젝트 소개

### My Personal Assistant (MPA)
**LLM 개발자가 직접 만든 나만의 AI 비서**

- 웹 검색 · 논문 탐색 · 코드 실행 · GitHub · Notion · 캘린더
- 모두 하나의 채팅창에서

**만든 이유**
> "AI 논문은 ArXiv에서, 메모는 Notion에서, 일정은 캘린더에서…
> 매일 여러 도구를 왔다갔다 하는 게 불편했다."

**데모**: https://mypersonalassistant-epcfckkzuvkjf6cwmmivk5.streamlit.app/

---

## Slide 2 — 전체 아키텍처

```
사용자
  │
  ▼
Streamlit Cloud (프론트엔드)
  │  HTTP
  ▼
FastAPI 백엔드 (Fly.io)
  │
  ▼
Orchestrator — gpt-5.2
  ├── research  (gpt-4o-mini)  웹 검색 · 논문
  ├── note      (gpt-4o-mini)  Notion
  ├── file      (gpt-4o-mini)  로컬 파일 ──→ MCP 서버 (로컬 + ngrok)
  ├── code      (gpt-4o)       코드 실행 ──→ Modal Sandbox
  ├── github    (gpt-4o-mini)  GitHub
  └── cron      (gpt-4o-mini)  자동 브리핑
        │
        ▼
   Neon PostgreSQL
   (대화 기억 · 장기 기억)
```

---

## Slide 3 — OpenClaw에서 영감, deepagents로 구현

**OpenClaw**: Orchestrator-Subagent 패턴의 개인 비서 프레임워크

**핵심 아이디어 그대로 가져온 것**
- Orchestrator가 요청을 받아 적절한 서브에이전트에 위임
- 비서 이름 짓기 (장기 기억)
- 자동 브리핑 크론잡

**deepagents로 구현한 이유**

| LangGraph 직접 구현 | deepagents |
|---------------------|------------|
| StateGraph, 노드, 엣지 수동 정의 | `create_deep_agent()` 한 줄 |
| 라우팅 로직 직접 작성 | LLM이 description 읽고 자동 판단 |
| ~100줄+ 보일러플레이트 | 선언적 dict 구조 |

> 사내 deepagents 세미나 → 실제 프로젝트에 적용

---

## Slide 4 — Orchestrator-Subagent 패턴

**라우팅 코드가 없다**

```python
# 오케스트레이터 등록만 하면 끝
agent = create_deep_agent(
    model="openai:gpt-5.2",
    subagents=[RESEARCH_SUBAGENT, NOTE_SUBAGENT, FILE_SUBAGENT,
               CODE_SUBAGENT, GITHUB_SUBAGENT, CRON_SUBAGENT],
    ...
)
```

```python
# LLM이 이 description을 읽고 언제 호출할지 판단
GITHUB_SUBAGENT = {
    "description": "GitHub 관련 작업이 필요할 때 사용. "
                   "담당 이슈 조회, PR 목록, 이슈 생성·댓글...",
    "tools": [list_my_issues, list_my_prs, create_issue, ...],
}
```

**서브에이전트별 모델 선택**
- Orchestrator: `gpt-5.2` — 복잡한 라우팅 판단
- 서브에이전트: `gpt-4o-mini` — 단순 실행, 비용 최적화
- code 서브에이전트만: `gpt-4o` — 코드 생성 품질

---

## Slide 5 — 툴 설계: docstring이 곧 API 문서

LLM이 툴을 선택하는 기준 = **docstring**

```python
def save_memory(key: str, value: str) -> str:
    """사용자 정보나 선호도를 장기 기억에 저장한다.
    나중에 다시 참조할 정보에 사용."""

def append_changelog(summary: str, files: str | None = None) -> str:
    """CHANGELOG.md에 오늘 날짜로 작업 내역을 기록한다.
    코드 실행, 파일 수정/생성, 중요한 작업 완료 시 호출한다."""
```

**툴은 그냥 Python 함수**
- 언제 호출할지 → LLM이 docstring 읽고 판단
- 파라미터에 뭘 넣을지 → LLM이 타입 힌트 + docstring 보고 결정
- docstring이 나쁘면 → 툴을 안 쓰거나 잘못 씀

---

## Slide 6 — 두 종류의 기억

```
단기 기억 (대화 히스토리)
  LangGraph Checkpointer
  ├── 로컬: MemorySaver (메모리, 재시작 시 초기화)
  └── 배포: AsyncPostgresSaver (Neon PostgreSQL, 영구 유지)
  → thread_id로 대화 세션 구분

장기 기억 (영구 저장)
  save_memory("assistant_name", "클로드")
  → DB INSERT / UPSERT
  → 대화가 끊겨도, 새 세션에서도 유지
  → get_memory()로 언제든 호출
```

**실제 동작 예시**
```
사용자: "너 이름은 아리야"
비서:   save_memory("assistant_name", "아리") 호출
        → 다음 대화, 재시작 후에도 "아리"로 기억
```

---

## Slide 7 — HITL (Human-in-the-Loop)

**에이전트 자율성 vs 사용자 통제**

```python
# 오케스트레이터 레벨 — 외부 서비스 생성
HITL_TOOLS = {
    "create_event": True,        # 캘린더 일정 생성
    "create_notion_page": True,  # Notion 페이지 생성
}

# 서브에이전트 레벨 — GitHub 쓰기 작업
"interrupt_on": {
    "create_issue": True,
    "comment_on_issue": True,
}
```

**동작 흐름**
```
에이전트가 create_event 호출 시도
  → LangGraph 그래프 실행 일시정지
  → Streamlit에 "승인 / 취소" 버튼 표시
  → 승인: ainvoke(None) 으로 재개
  → 취소: ToolMessage("취소됨") 주입 후 재개
```

> "읽기는 자동, 쓰기는 확인" 원칙

---

## Slide 8 — MCP 서버 & 보안

**문제**: Streamlit Cloud · Fly.io에서 로컬 맥북 파일에 접근 불가

**해결**: 로컬 MCP 서버 + ngrok 터널

```
맥북 MCP 서버 (port 8002)
  └→ ngrok 고정 도메인
       └→ Fly.io 에이전트가 HTTP 요청
```

**보안 이중화**

```yaml
# mcp_server/config.yaml
deny:                    # 읽기 자체를 차단
  - ".env"
  - ".env.*"
  - "*.key"
ignore:                  # 목록에서만 숨김
  - ".venv"
  - ".git"
  - "__pycache__"
```

| | deny | ignore |
|--|------|--------|
| 목록에 표시 | X | X |
| 파일 읽기 | X | O |

---

## Slide 9 — 코드 실행: Modal Sandbox

**왜 샌드박스가 필요한가**
- 에이전트가 생성한 코드를 서버에서 직접 실행하면 위험
- Modal의 격리된 클라우드 컨테이너에서 실행

```python
# 팩토리 클로저 — 샌드박스 재사용 + 만료 시 자동 재생성
def _make_sandbox_factory():
    _sandbox = None

    def factory(runtime):
        nonlocal _sandbox
        if not _is_alive(_sandbox):   # 죽어있으면 새로 생성
            _sandbox = modal.Sandbox.create(...)
        return ModalSandbox(sandbox=_sandbox)

    return factory
```

**동작 예시**
```
사용자: "피보나치 100번째 숫자 계산해줘"
에이전트: /root/script.py 작성 → execute("python /root/script.py")
          → 결과 반환
```

---

## Slide 10 — 배포 구조

| 서비스 | 플랫폼 | 비용 | 선택 이유 |
|--------|--------|------|-----------|
| 프론트엔드 | Streamlit Cloud | 무료 | Python 서버, GitHub 자동 배포 |
| 백엔드 | Fly.io | ~$2/월 | 24/7 크론잡, Docker, WebSocket |
| DB | Neon PostgreSQL | 무료 | 비활성 슬립, dev/prod 기억 공유 |
| 코드 실행 | Modal | 종량제 | 격리 샌드박스, 자동 확장 |
| 파일 접근 | 로컬 + ngrok | 무료 | 로컬 파일을 외부에 안전하게 노출 |

**CI/CD**
- GitHub Actions: mypy + ruff + pytest 통과 시 Fly.io 자동 배포
- Streamlit Cloud: main 브랜치 push 시 자동 재배포

---

## Slide 11 — 개선점 & 다음 단계

**현재 한계**
- MCP 서버는 맥북이 켜져 있을 때만 동작
- Modal Sandbox 초기 생성에 시간 소요 (최초 30~60초)
- 테스트 커버리지: 핵심 툴 위주, 에이전트 통합 테스트 미비

**추가하고 싶은 것**
- 슬랙 알림 연동 (브리핑 결과 푸시)
- 음성 입력 (Whisper API)
- 멀티 유저 지원 (thread_id를 사용자 ID로 분리)
- 에이전트 평가 파이프라인 (LangSmith)
