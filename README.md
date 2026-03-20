# My Personal Assistant (MPA)

LLM 전문 AI 개발자를 위한 개인 비서. 웹 검색, 논문 탐색, 메모 관리, 자동 브리핑을 하나의 채팅 인터페이스에서 제공합니다.

**[데모 바로가기 →](https://mypersonalassistant-epcfckkzuvkjf6cwmmivk5.streamlit.app/)**

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 웹 검색 | Tavily API 기반 최신 정보 검색 |
| 논문 탐색 | ArXiv · HuggingFace Daily Papers 수집 및 요약 |
| 메모 관리 | 메모 저장, 검색, 조회 |
| 로컬 파일 분석 | MCP 서버를 통한 로컬 파일 읽기 |
| 자동 브리핑 | 매일 10:00 논문 브리핑, 매주 금요일 17:00 주간 리포트 자동 생성 |
| 비서 이름 짓기 | 대화 중 비서에게 이름을 부여하고 장기 기억으로 유지 |
| API 비용 확인 | 이번 달 OpenAI API 사용 비용 조회 |
| HITL | 파일 수정·생성·코드 실행 전 사용자 확인 요청 |

> 비서 이름 짓기와 크론잡 자동 브리핑은 [OpenClaw](https://github.com/OpenClaw)에서 영감을 받아 구현했습니다.

---

## 스크린샷

<!-- TODO: Streamlit UI 스크린샷 추가 (docs/screenshots/) -->

---

## 아키텍처

```
사용자 (Streamlit Cloud)
  └→ Orchestrator (gpt-5.2 / Thinking mode)
       ├→ research 서브에이전트 (gpt-4o-mini) — 웹 검색, 논문 탐색
       ├→ note 서브에이전트 (gpt-4o-mini)     — 메모 저장/조회/수정
       ├→ file 서브에이전트 (gpt-4o-mini)     — 로컬 파일 읽기
       └→ cron 서브에이전트 (gpt-4o-mini)     — 브리핑/리포트 생성

FastAPI 백엔드 (Fly.io)
  ├→ APScheduler — 크론잡 (브리핑, 리포트)
  └→ REST API    — 메모, 논문, 비용 조회

로컬 MCP 서버 (포트 8002)
  └→ ngrok 터널 → Fly.io 백엔드에서 로컬 파일 접근
```

---

## 배포 구조 & 기술 선택 이유

| 서비스 | 플랫폼 | 이유 |
|--------|--------|------|
| 프론트엔드 | Streamlit Cloud (무료) | Python 서버 무료 배포, GitHub 연동 자동 배포 |
| 백엔드 | Fly.io (~$2/월) | 크론잡이 24/7 실행되어야 함, Docker 기반, WebSocket 지원 |
| DB | Neon PostgreSQL (무료) | 비활성 시 자동 슬립으로 무료 티어 유지, dev/prod 동일 DB로 기억 공유 |
| MCP 서버 | 로컬 + ngrok | 배포된 백엔드에서 로컬 파일에 접근하기 위한 터널 |

---

## 설치 및 실행

### 요구사항
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [ngrok](https://ngrok.com/) (로컬 파일 접근 시)

### 로컬 실행

```bash
# 의존성 설치
uv sync

# 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 백엔드
uv run --env-file .env uvicorn backend.app:app --reload --port 8000

# 프론트엔드
uv run --env-file .env streamlit run frontend/app.py --server.port 8001

# MCP 서버 (로컬 파일 접근 시)
uv run --env-file .env python mcp_server/main.py
# 새 터미널에서
ngrok http 8002 --domain=<your-ngrok-domain>
```

---

## 환경변수

`.env.example`을 복사해 `.env`를 만들고 아래 값을 채우세요.

| 변수 | 설명 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `TAVILY_API_KEY` | Tavily 검색 API 키 ([무료 1,000회/월](https://tavily.com)) |
| `DATABASE_URL` | Neon PostgreSQL 연결 문자열 (없으면 SQLite 자동 사용) |
| `MCP_SERVER_URL` | MCP 서버 URL (dev: `http://localhost:8002`, prod: ngrok URL) |
| `MCP_AUTH_TOKEN` | MCP 서버 인증 토큰 |

---

## 개발 워크플로우

```bash
# 타입 체크
uv run mypy .

# 린트 & 포맷
uv run ruff check . && uv run ruff format .

# 테스트
uv run pytest tests/ -v
```

main 브랜치에 push하면 CI(lint + test) 통과 후 Fly.io에 자동 배포됩니다.

---

## 기술 스택

- **에이전트**: [deepagents](https://github.com/langchain-ai/deepagents) (LangChain + LangGraph)
- **백엔드**: FastAPI + APScheduler
- **프론트엔드**: Streamlit
- **DB**: PostgreSQL (Neon) / SQLite (로컬)
- **MCP**: fastmcp
- **배포**: Fly.io + Streamlit Cloud

### LangGraph 대신 deepagents를 쓴 이유

LangGraph로 직접 구현하면 StateGraph, 노드, 엣지를 모두 수동으로 정의해야 합니다. deepagents는 이를 추상화해 `create_deep_agent()` 한 줄로 Orchestrator-Subagent 구조를 빠르게 구성할 수 있습니다. 사내 deepagents 세미나를 계기로 실제 프로덕션 수준의 프로젝트에 적용해보는 것이 목적이기도 했습니다.
