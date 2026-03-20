# My Personal Assistant (MPA)

LLM 전문 AI 개발자를 위한 개인 비서.
deepagents(LangChain + LangGraph) 기반, Fly.io 배포.

## 커맨드

```bash
uv add <package>          # 패키지 추가 (pip 금지)
uv sync                   # 의존성 설치
uv run uvicorn backend.app:app --reload --port 8000
uv run chainlit run frontend/app.py --port 8001
uv run python mcp_server/main.py --port 8002
uv run mypy .             # 타입 체크
uv run ruff check . && uv run ruff format .
uv run pytest tests/ -v
```

## 개발 Workflow

1. 새 기능은 `tests/`에 테스트 먼저 작성
2. 구현 후 `uv run mypy .` → `uv run ruff check .` → `uv run pytest tests/ -v` 순서로 검증
3. 세 가지 모두 통과해야 완료로 간주
4. 새 툴 추가 시 → docstring 필수 작성 후 에이전트에 등록

## 아키텍처

```
Orchestrator (gpt-5.2 / Thinking mode)
  └── Subagents (gpt-4o-mini): research / note / file / cron
        └── Tools: @tools/search.py @tools/papers.py @tools/notes.py @tools/memory.py @tools/local_file.py

FastAPI (async + WebSocket) → Chainlit UI
로컬 MCP 서버 (포트 8002) ← ngrok Tunnel → Fly.io 서버 (https://mpa-jm.fly.dev)
APScheduler: 매일 10:00 논문 브리핑, 매주 금요일 17:00 주간 리포트
```

상세 설계: @agent/orchestrator.py @backend/app.py

## 코딩 컨벤션

- Python 3.13+, 타입 힌트 필수
- `Literal` 사용 (`Enum` 금지)
- FastAPI 엔드포인트는 반드시 `async def`
- 툴 함수 docstring 한국어로 작성 (LLM 툴 선택 근거)
- DB 직접 쿼리 금지 → 함수 레이어 통해 접근
- 구체적인 예외 처리 (`except Exception` 지양)

## IMPORTANT

- `pip install` 금지 → `uv add` 사용
- 환경 변수 하드코딩 금지 → `.env`에서만 로드
- MCP 서버 허용 디렉토리(`mcp_server/config.yaml`) 외 경로 절대 노출 금지
- 백그라운드 작업 완료 시 WebSocket으로 채팅창에 자동 푸시
- HITL 필수 액션 (실행 전 사용자 확인): `edit_file`, `write_file`, `execute`, 로컬 MCP 쓰기
- HITL 불필요 액션 (자동 실행): 웹 검색, 논문 수집, 메모 저장/조회

## 환경 변수 (.env)

```
OPENAI_API_KEY=
TAVILY_API_KEY=        # 무료 1,000회/월 (https://tavily.com)
# DATABASE_URL=  # 로컬 비워두기. Fly.io 배포 시만 postgresql:// 형식으로 설정
MCP_SERVER_URL=   # ngrok 고정 도메인 (예: https://xxx.ngrok-free.app)
MCP_AUTH_TOKEN=
```

---
- 서브에이전트 모델 설정 시 실제 접근 가능한 모델인지 확인 필요. `gpt-5.3-instant`는 접근 불가 확인됨 → 서브에이전트는 `gpt-4o-mini` 사용
- `.dockerignore`에서 `storage/` 전체 제외 금지 → `storage/db.py` 등 소스코드까지 제외됨. DB 파일만 제외: `storage/*.db`, `storage/*.json`
- Docker에서 로컬 패키지 인식 안 될 때 → `ENV PYTHONPATH=/app` 으로 해결 (`uv pip install -e .` 단독으로는 불충분)
- Fly.io 배포: `pyproject.toml`의 `[tool.setuptools.packages.find] exclude`에서 로컬 패키지 이름 제외 금지
- Fly.io 배포: `uv run uvicorn` 대신 `.venv/bin/uvicorn` 직접 사용 (런타임 재동기화 방지)

*Claude가 실수하면 이 파일을 업데이트해서 같은 실수를 반복하지 않도록 한다.*
