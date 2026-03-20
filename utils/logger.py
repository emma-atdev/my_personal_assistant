"""에이전트 로깅 — 모델 호출, 응답, 툴 실행을 콘솔과 파일에 기록한다."""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

# ── 로거 설정 ──────────────────────────────────────────────────

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 콘솔 핸들러
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_console.setLevel(logging.INFO)

# 파일 핸들러 (최대 10MB × 5개 롤링)
_file = RotatingFileHandler(
    LOG_DIR / "agent.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file.setFormatter(_fmt)
_file.setLevel(logging.DEBUG)

agent_logger = logging.getLogger("mpa.agent")
agent_logger.setLevel(logging.DEBUG)
agent_logger.addHandler(_console)
agent_logger.addHandler(_file)
agent_logger.propagate = False


# ── CallbackHandler ────────────────────────────────────────────


class AgentLoggingHandler(BaseCallbackHandler):
    """모델 호출, 응답, 툴 실행을 로깅하는 LangChain 콜백 핸들러."""

    def __init__(self) -> None:
        super().__init__()
        self._start_times: dict[str, float] = {}

    # ── LLM ───────────────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model_name = (serialized or {}).get("kwargs", {}).get("model_name", "unknown")
        self._start_times[str(run_id)] = time.perf_counter()

        # 마지막 사용자 메시지만 요약 (str / BaseMessage 모두 처리)
        last_msg = ""
        if messages and messages[0]:
            last = messages[0][-1]
            last_msg = str(getattr(last, "content", last))[:200]

        agent_logger.info("LLM 호출 | 모델: %s | 입력: %s", model_name, last_msg)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        elapsed = time.perf_counter() - self._start_times.pop(str(run_id), time.perf_counter())

        # 토큰 사용량
        usage = {}
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})

        # 응답 텍스트 요약
        output_text = ""
        if response.generations and response.generations[0]:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            msg_content = getattr(msg, "content", None)
            content = getattr(gen, "text", "") or (str(msg_content) if msg_content is not None else "")
            output_text = content[:300]

        agent_logger.info(
            "LLM 응답 | %.2f초 | 입력 %s토큰 | 출력 %s토큰 | 응답: %s",
            elapsed,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            output_text,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._start_times.pop(str(run_id), None)
        agent_logger.error("LLM 오류: %s", error)

    # ── Tool ───────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        self._start_times[f"tool_{run_id}"] = time.perf_counter()
        agent_logger.info("툴 실행 | %s | 입력: %s", tool_name, input_str[:200])

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        elapsed = time.perf_counter() - self._start_times.pop(f"tool_{run_id}", time.perf_counter())
        agent_logger.info("툴 완료 | %.2f초 | 결과: %s", elapsed, str(output)[:300])

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._start_times.pop(f"tool_{run_id}", None)
        agent_logger.error("툴 오류: %s", error)

    # ── Chain ──────────────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name", "chain")
        agent_logger.debug("체인 시작 | %s", name)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        agent_logger.debug("체인 완료")
