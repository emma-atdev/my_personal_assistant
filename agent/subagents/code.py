"""코드 실행 서브에이전트 — Modal Sandbox 백엔드 사용."""

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent
from langchain.chat_models import init_chat_model

_CODE_SYSTEM_PROMPT = (
    "당신은 Python 전문 코드 실행 에이전트입니다.\n"
    "Modal 클라우드 샌드박스 안에서 격리된 환경으로 코드를 실행합니다.\n\n"
    "작업 방식:\n"
    "1. write()로 /root/script.py 파일에 코드 작성\n"
    "2. execute()로 실행: `python /root/script.py`\n"
    "3. 필요하면 패키지 설치 후 실행: `pip install -q numpy && python /root/script.py`\n\n"
    "주의사항:\n"
    "- 호스트 파일, 환경변수, API 키에 접근할 수 없습니다\n"
    "- 코드 실행 결과를 그대로 전달하고 간략히 해석해 주세요"
)

_MODAL_APP_NAME = "personal-assistant-sandbox"


def _make_code_subagent() -> CompiledSubAgent:
    """Modal Sandbox 백엔드를 가진 코드 실행 서브에이전트를 생성한다."""
    try:
        import modal
        from langchain_modal import ModalSandbox

        app = modal.App.lookup(_MODAL_APP_NAME, create_if_missing=True)
        sandbox = modal.Sandbox.create(app=app, timeout=300)
        backend: ModalSandbox | None = ModalSandbox(sandbox=sandbox)
    except Exception:  # noqa: BLE001
        # Modal 미설정 또는 미설치 시 backend 없이 진행
        backend = None

    agent = create_deep_agent(
        model=init_chat_model("openai:gpt-4o-mini"),
        system_prompt=_CODE_SYSTEM_PROMPT,
        backend=backend,
        interrupt_on={"execute": True},
        name="code-executor",
    )

    return CompiledSubAgent(
        name="code",
        description=(
            "Python 코드 작성·실행 또는 수학 계산·데이터 분석이 필요할 때 사용. "
            "Modal 클라우드 샌드박스 안에서 안전하게 실행하며 중간 결과를 반환."
        ),
        runnable=agent,
    )


CODE_SUBAGENT = _make_code_subagent()
