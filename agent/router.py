"""쿼리 라우터 — 간단한 대화와 복잡한 작업을 분류하고 쿼리를 재작성한다."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from utils.logger import agent_logger

_ROUTER_SYSTEM = """\
당신은 AI 비서의 쿼리 라우터입니다. 사용자 메시지를 분석해 JSON만 반환하세요. 설명 없음.

분류 기준:
- simple: 인사, 감사, 짧은 반응("응", "알겠어"), 이전 대화 내용에 대한 간단한 코멘트
- complex: 검색, 파일, 캘린더, 코드 실행, Notion, GitHub, 논문, 날씨, 최신 정보, 메모, 계산 등 도구가 필요한 모든 것

simple 응답 형식:
{"type": "simple", "response": "한국어 답변"}

complex 응답 형식:
{"type": "complex", "rewritten": "원문 또는 대명사 해소·의도 명확화한 쿼리"}
- 이미 명확하면 원문 그대로 넣을 것
- 대화 맥락에서 "그거", "아까", "방금" 등의 지시어가 있으면 구체적으로 풀어쓸 것\
"""


def _filter_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """라우터 컨텍스트용 — HumanMessage와 텍스트 AIMessage만 최근 8개 남긴다."""
    result: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append(HumanMessage(content=str(msg.content)))
        elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            content = msg.content
            if isinstance(content, list):
                text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            else:
                text = str(content)
            if text:
                result.append(AIMessage(content=text))
    return result[-8:]


async def route(message: str, history: list[BaseMessage]) -> dict[str, Any]:
    """쿼리를 분류한다.

    Returns:
        simple: {"type": "simple", "response": str}
        complex: {"type": "complex", "rewritten": str}
    """
    from auth.langchain_chatgpt import get_model
    from utils.logger import AgentLoggingHandler

    model = get_model(pkce_model="gpt-5.1-codex-mini", openai_fallback="openai:gpt-4o-mini")
    ctx = _filter_history(history)
    messages = [SystemMessage(content=_ROUTER_SYSTEM), *ctx, HumanMessage(content=message)]

    try:
        result = await model.ainvoke(messages, config={"callbacks": [AgentLoggingHandler()]})
        raw = result.content if hasattr(result, "content") else str(result)
        raw = raw.strip()
        # 마크다운 코드블록 제거
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
        data: dict[str, Any] = json.loads(raw)
        if data.get("type") == "simple":
            agent_logger.info("라우터 → simple | 쿼리: %s", message[:100])
            return data
        if data.get("type") == "complex":
            rewritten = data.get("rewritten", message)
            if rewritten != message:
                agent_logger.info("라우터 → complex (재작성) | 원문: %s | 재작성: %s", message[:100], rewritten[:100])
            else:
                agent_logger.info("라우터 → complex | 쿼리: %s", message[:100])
            return data
    except Exception as e:  # noqa: BLE001
        agent_logger.warning("라우터 파싱 실패 → complex 폴백 | 오류: %s", e)

    return {"type": "complex", "rewritten": message}
