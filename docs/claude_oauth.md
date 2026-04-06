# Claude.ai OAuth 통합 가이드

Claude.ai 구독을 활용해 Anthropic API 키 없이 오케스트레이터를 실행하는 방법.

---

## 왜 이 방식을 쓰는가

| 항목 | Anthropic API 키 | Claude.ai OAuth |
|------|----------------|----------------|
| 과금 | 토큰당 종량제 | Pro/Max 월 정액 |
| 모델 | claude-sonnet-4-6 등 | claude-sonnet-4-6, claude-opus-4-6 등 |
| 안정성 | 공식 API, SLA 보장 | 비공식 — 스펙 변경 시 깨질 수 있음 |
| 설정 난이도 | API 키 발급만 | not-claude-code-emulator 설치 필요 |

---

## 아키텍처

```
get_model(oauth_model, anthropic_fallback)       ← auth/langchain_claude.py
  ├── ~/.config/anthropic/q/tokens.json 있음
  │     └── localhost:3000 에뮬레이터 실행 중
  │           → ChatAnthropic(base_url="http://localhost:3000")
  └── 토큰 없음 또는 에뮬레이터 미실행
        → init_chat_model(anthropic_fallback)

오케스트레이터 → get_model("claude-sonnet-4-6", "anthropic:claude-sonnet-4-6")

not-claude-code-emulator (localhost:3000)
  └── Claude Code CLI 스푸핑 → OAuth 토큰 + cch 서명 처리
        └── POST https://api.anthropic.com/v1/messages
              Headers: Authorization: Bearer <access_token>
              Body: Claude Code 서명(fingerprint, cch) 포함
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `auth/claude_pkce.py` | OAuth 토큰 로드 (`~/.config/anthropic/q/tokens.json`) |
| `auth/langchain_claude.py` | `get_model()` 팩토리 — 프록시 모델 또는 API 폴백 |
| `agent/orchestrator.py` | `_get_model()` → Claude OAuth 1순위 |
| `~/.config/anthropic/q/tokens.json` | 액세스/리프레시 토큰 저장 (gitignore 등록됨) |
| `~/.config/not-claude-code-emulator/install-consent.json` | 에뮬레이터 GitHub star 동의 파일 |

---

## 최초 설정

### 1. not-claude-code-emulator 설치

```bash
npx not-claude-code-emulator@latest install
```

GitHub star 확인 팝업이 뜨면 실제로 star를 누르거나, 아래처럼 수동으로 동의 파일 생성:

```bash
mkdir -p ~/.config/not-claude-code-emulator
echo '{"starred": true, "updatedAt": "2026-04-02T00:00:00.000Z"}' \
  > ~/.config/not-claude-code-emulator/install-consent.json
```

설치 완료 시 토큰이 `~/.config/anthropic/q/tokens.json`에 저장된다.

### 2. 에뮬레이터 실행

```bash
npx not-claude-code-emulator@latest start
```

`🚀 Starting server...` 후 `localhost:3000`에서 실행 중 메시지가 나오면 준비 완료.

> **주의**: Bun 서버가 IPv6(`::1`)에 바인딩되므로 `127.0.0.1`로는 접속 안 된다.
> `auth/langchain_claude.py`의 `_is_proxy_running()`이 IPv4/IPv6 모두 시도하도록 구현되어 있다.

### 3. 동작 확인

```bash
uv run python -c "
from auth.langchain_claude import get_model
model = get_model()
result = model.invoke('안녕! 한 줄로만 답해줘.')
print(result.content)
"
```

---

## 토큰 관리

토큰 파일 위치: `~/.config/anthropic/q/tokens.json`

```json
{
  "accessToken": "sk-ant-oat01-...",
  "refreshToken": "...",
  "expiresAt": 1234567890000
}
```

- `expiresAt`: 밀리초 단위 Unix timestamp
- 에뮬레이터가 토큰 갱신을 자동으로 처리

토큰 만료 또는 재로그인 필요 시:
```bash
npx not-claude-code-emulator@latest install
```

---

## 어떻게 구현 방법을 찾았나 — not-claude-code-emulator 분석

### 배경

Claude.ai OAuth 토큰(`sk-ant-oat01-...`)은 `Authorization: Bearer` 헤더로 전송해야 하는데,
`langchain-anthropic`의 `ChatAnthropic`은 `x-api-key` 헤더만 사용해서 직접 연동 불가.

직접 `anthropic.AsyncAnthropic(auth_token=...)` + cch 서명 구현을 시도했으나
429 Rate Limit가 지속되어 프록시 방식으로 전환.

### not-claude-code-emulator 역할

[not-claude-code-emulator](https://github.com/code-yeongyu/not-claude-code-emulator)는
Claude Code CLI를 스푸핑해서 claude.ai 구독으로 Anthropic API를 호출하는 로컬 프록시.

처리하는 것들:
- OAuth Bearer 토큰을 `x-api-key` 대신 `Authorization: Bearer`로 전송
- Claude Code 빌링 헤더 주입 (`x-anthropic-billing-header`)
- cch 서명 계산 (xxHash64 기반 body signing)
- fingerprint 계산 (`SHA256` 기반)

### 프록시 연결 방식

```python
# auth/langchain_claude.py
ChatAnthropic(
    model_name="claude-sonnet-4-6",
    api_key="sk-ant-placeholder00",   # 더미 키 (에뮬레이터가 교체)
    base_url="http://localhost:3000", # 에뮬레이터 프록시
)
```

`ChatAnthropic`이 `localhost:3000`으로 요청을 보내면 에뮬레이터가 OAuth 서명 후 실제 API에 전달.

---

## 모델 우선순위 (orchestrator.py)

```
1순위: Claude.ai OAuth (토큰 + 에뮬레이터 실행 시)
  → claude-sonnet-4-6

2순위: ChatGPT Plus PKCE (.chatgpt_tokens.json 있을 시)
  → gpt-5.2

3순위: OpenAI API 폴백 (OPENAI_API_KEY)
  → openai:gpt-5.2
```

---

## 지원 모델

| 모델 ID | 용도 |
|---------|------|
| `claude-sonnet-4-6` | 오케스트레이터 기본값 |
| `claude-opus-4-6` | 고성능 필요 시 |
| `claude-haiku-4-5` | 경량 빠른 응답 |

---

## 깨지는 경우 대처

| 증상 | 원인 | 대처 |
|------|------|------|
| `get_model()` → API 폴백으로 동작 | 에뮬레이터 미실행 | `npx not-claude-code-emulator@latest start` |
| `get_model()` → API 폴백으로 동작 | 토큰 파일 없음 | `npx not-claude-code-emulator@latest install` |
| `connection refused` (port 3000) | Bun IPv6 바인딩 | `_is_proxy_running()` IPv6 체크 이미 구현됨 |
| `429 Rate Limit` | 에뮬레이터 없이 직접 호출 | 반드시 에뮬레이터 통해서 호출할 것 |
| `401 Unauthorized` | 토큰 만료 | 에뮬레이터 재실행 (자동 갱신) 또는 재설치 |

---

## health check

```bash
# 토큰 존재 확인
python -c "from auth.claude_pkce import load_tokens; print(load_tokens())"

# 에뮬레이터 실행 확인
python -c "from auth.langchain_claude import _is_proxy_running; print(_is_proxy_running())"

# 모델 호출 테스트
uv run python -c "
from auth.langchain_claude import get_model
model = get_model()
print(type(model).__name__)
result = model.invoke('say hi in one word')
print(result.content)
"
```
