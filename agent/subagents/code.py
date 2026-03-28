"""코드 실행 서브에이전트 — Modal Sandbox 백엔드 사용."""

import atexit
import warnings
from typing import Any

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent

from auth.langchain_chatgpt import get_model

_CODE_SYSTEM_PROMPT = (
    "당신은 Python 코드 실행 에이전트입니다. 반드시 한국어로 답변하세요.\n"
    "반드시 아래 순서를 지켜야 합니다. 절대 머릿속으로 계산하거나 추측하지 마세요.\n\n"
    "필수 실행 순서 (예외 없음):\n"
    "1. /root/script.py에 Python 코드 작성\n"
    "   - 파일이 없으면 write_file로 생성\n"
    "   - 파일이 이미 존재하면 반드시 edit_file로 전체 내용을 교체 (write_file 금지)\n"
    "2. execute()로 실행: `python /root/script.py`\n"
    "3. 필요하면 패키지 설치 후 실행: `pip install -q numpy && python /root/script.py`\n"
    "4. execute() 결과를 그대로 사용자에게 전달\n\n"
    "금지 사항:\n"
    "- 코드를 실행하지 않고 답을 직접 작성하는 것\n"
    "- /root/script.py 이외의 경로에 스크립트 파일을 만드는 것\n"
    "- execute() 없이 작업을 완료하는 것\n"
    "- shell script(.sh) 파일 생성\n"
    "- task 툴로 다른 에이전트에 실행을 위임하는 것 — 반드시 execute()를 직접 호출\n\n"
    "주의사항:\n"
    "- 호스트 파일, 환경변수, API 키에 접근할 수 없습니다\n"
    "- 실행 결과를 그대로 전달하고 간략히 해석해 주세요"
)

_MODAL_APP_NAME = "personal-assistant-sandbox"


def _make_sandbox_factory() -> tuple[Any, Any]:
    """샌드박스 팩토리 클로저 — 만료 시 자동 재생성. (factory, stop) 튜플 반환."""
    _sandbox: Any = None
    _backend: Any = None

    def _is_alive() -> bool:
        if _sandbox is None:
            return False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return _sandbox.poll() is None
        except Exception:  # noqa: BLE001
            return False

    def factory(runtime: Any) -> Any:
        nonlocal _sandbox, _backend
        if not _is_alive():
            import asyncio
            import threading

            import modal
            from langchain_modal import ModalSandbox

            async def _create() -> Any:
                app = await modal.App.lookup.aio(_MODAL_APP_NAME, create_if_missing=True)
                return await modal.Sandbox.create.aio(app=app, timeout=300)

            result: list[Any] = []
            error: list[BaseException] = []

            def _run() -> None:
                loop = asyncio.new_event_loop()
                try:
                    result.append(loop.run_until_complete(_create()))
                except BaseException as e:  # noqa: BLE001
                    error.append(e)
                finally:
                    loop.close()

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=60)

            if error:
                raise error[0]
            _sandbox = result[0]
            _backend = ModalSandbox(sandbox=_sandbox)
            atexit.register(_stop)

        return _backend

    def _stop() -> None:
        if _sandbox is not None and _is_alive():
            try:
                _sandbox.stop()
            except Exception:  # noqa: BLE001
                pass

    return factory, _stop


def _make_code_subagent() -> tuple[CompiledSubAgent, Any]:
    """Modal Sandbox 백엔드를 가진 코드 실행 서브에이전트를 생성한다. (subagent, stop) 튜플 반환."""
    stop: Any = None
    try:
        backend, stop = _make_sandbox_factory()
    except Exception:  # noqa: BLE001
        backend = None

    agent = create_deep_agent(
        model=get_model(pkce_model="gpt-5.1", openai_fallback="openai:gpt-4o"),
        system_prompt=_CODE_SYSTEM_PROMPT,
        backend=backend,
        name="code-executor",
    )

    subagent = CompiledSubAgent(
        name="code",
        description=(
            "Python 코드 작성·실행 또는 수학 계산·데이터 분석이 필요할 때 사용. "
            "Modal 클라우드 샌드박스 안에서 안전하게 실행하며 중간 결과를 반환."
        ),
        runnable=agent,
    )
    return subagent, stop


CODE_SUBAGENT, _stop_sandbox = _make_code_subagent()


def stop_sandbox() -> None:
    """FastAPI lifespan 종료 시 Modal 샌드박스를 즉시 해제한다."""
    if _stop_sandbox is not None:
        _stop_sandbox()
