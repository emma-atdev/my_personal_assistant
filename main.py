"""개인 비서 CLI 진입점."""

import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from agent.orchestrator import create_orchestrator

load_dotenv()

console = Console()


def _get_last_ai_message(result: dict[str, object]) -> str:
    """에이전트 응답에서 마지막 AI 메시지 텍스트를 추출한다."""
    messages = result.get("messages", [])
    if not isinstance(messages, list):
        return "(응답 없음)"
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content
            if isinstance(content, list):
                return " ".join(block.get("text", "") for block in content if isinstance(block, dict))
            return str(content)
    return "(응답 없음)"


def handle_hitl(agent: CompiledStateGraph, config: RunnableConfig) -> str:  # type: ignore[type-arg]
    """HITL 인터럽트 처리 — 사용자 확인 후 에이전트를 재개한다."""
    console.print("\n[yellow]확인이 필요합니다[/yellow]")

    state = agent.get_state(config)
    pending = [t.name for t in state.tasks] if state.tasks else []
    if pending:
        console.print(f"[dim]실행 예정 툴: {', '.join(pending)}[/dim]")

    choice = Prompt.ask("진행할까요?", choices=["y", "n"], default="y")

    if choice == "n":
        result: dict[str, object] = agent.invoke(None, config)
        return "(취소됐습니다.)"

    result = agent.invoke(None, config)
    return _get_last_ai_message(result)


def chat_loop() -> None:
    """CLI 대화 루프."""
    console.print(
        Panel.fit(
            "[bold cyan]My Personal Assistant[/bold cyan]\n[dim]종료: exit 또는 Ctrl+C[/dim]",
            border_style="cyan",
        )
    )

    agent, config = create_orchestrator()

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]나[/bold green]")

            if user_input.strip().lower() in ("exit", "quit", "종료"):
                console.print("[dim]종료합니다.[/dim]")
                break

            if not user_input.strip():
                continue

            with console.status("[dim]생각 중...[/dim]", spinner="dots"):
                result: dict[str, object] = agent.invoke(
                    {"messages": [HumanMessage(content=user_input)]},
                    config,
                )

            # HITL 인터럽트 확인
            state = agent.get_state(config)
            if state.next:
                response = handle_hitl(agent, config)
            else:
                response = _get_last_ai_message(result)

            console.print("\n[bold blue]비서[/bold blue]")
            console.print(Markdown(response))

        except KeyboardInterrupt:
            console.print("\n[dim]종료합니다.[/dim]")
            break
        except Exception as e:
            console.print(f"[red]오류: {e}[/red]")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.[/red]")
        raise SystemExit(1)

    chat_loop()
