"""코드 실행 서브에이전트 — DockerSandbox(BaseSandbox) 백엔드 사용."""

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent
from langchain.chat_models import init_chat_model

from tools.sandbox import DockerSandbox

_CODE_SYSTEM_PROMPT = (
    "당신은 Python 전문 코드 실행 에이전트입니다.\n"
    "Docker 컨테이너 안에서 격리된 환경으로 코드를 실행합니다.\n\n"
    "작업 방식:\n"
    "1. write()로 /workspace/script.py 파일에 코드 작성\n"
    "2. execute()로 실행: `python /workspace/script.py`\n"
    "3. 필요하면 패키지 설치 후 실행: `pip install -q numpy && python /workspace/script.py`\n\n"
    "주의사항:\n"
    "- 호스트 파일, 환경변수, API 키에 접근할 수 없습니다\n"
    "- 실행 시간 30초, 메모리 512MB 제한\n"
    "- 네트워크 차단 상태 (pip install은 가능)\n"
    "- 코드 실행 결과를 그대로 전달하고 간략히 해석해 주세요"
)


def _make_code_subagent() -> CompiledSubAgent:
    """DockerSandbox 백엔드를 가진 코드 실행 서브에이전트를 생성한다."""
    try:
        backend = DockerSandbox()
    except RuntimeError:
        # Docker가 없으면 서브에이전트 생성 자체를 실패시키지 않고 None backend로 진행
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
            "Docker 샌드박스 안에서 안전하게 실행하며 중간 결과를 반환."
        ),
        runnable=agent,
    )


CODE_SUBAGENT = _make_code_subagent()
