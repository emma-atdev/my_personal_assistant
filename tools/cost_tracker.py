"""API 비용 추적 툴 — 모델별 토큰 사용량과 비용을 DB에 기록한다."""

from datetime import datetime

from storage.db import PH, get_conn, now_kst

# 모델별 1토큰당 USD 비용
PRICING: dict[str, dict[str, float]] = {
    "gpt-5.2": {"input": 1.75 / 1_000_000, "output": 14.0 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.0 / 1_000_000},
}

# ChatGPT Plus PKCE OAuth로 사용하는 모델 (정액제 — 토큰당 과금 없음)
_PKCE_MODELS: frozenset[str] = frozenset(
    [
        "gpt-5.1",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex-max",
        "gpt-5.2",
        "gpt-5.2-codex",
        "gpt-5.3-codex",
        "gpt-5.4",
    ]
)


def _get_pricing(model: str) -> dict[str, float]:
    """모델명으로 가격 정보를 반환한다. 정확히 없으면 prefix로 매칭한다."""
    # "openai:gpt-5.2" → "gpt-5.2" 정규화
    normalized = model.split(":")[-1] if ":" in model else model
    if normalized in PRICING:
        return PRICING[normalized]
    # "gpt-5.2-2025-12-11" 같은 버전 suffix 대응
    for key in PRICING:
        if normalized.startswith(key):
            return PRICING[key]
    return {"input": 0.0, "output": 0.0}


def log_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """API 토큰 사용량을 기록한다 (내부 사용)."""
    pricing = _get_pricing(model)
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    with get_conn() as con:
        con.execute(
            f"INSERT INTO cost_logs (date, model, input_tokens, output_tokens, cost_usd)"
            f" VALUES ({PH}, {PH}, {PH}, {PH}, {PH})",
            (now_kst(), model, input_tokens, output_tokens, round(cost, 6)),
        )


def _normalize_model(model: str) -> str:
    """'openai:gpt-4o-mini' → 'gpt-4o-mini' 정규화."""
    return model.split(":")[-1] if ":" in model else model


def get_cost_summary() -> str:
    """이번 달 API 비용 및 토큰 사용량 요약을 반환한다. 비용 확인이 필요할 때 사용."""
    current_month = datetime.now().strftime("%Y-%m")

    with get_conn() as con:
        if PH == "%s":
            rows = con.execute(
                "SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as out, SUM(cost_usd) as total"
                " FROM cost_logs WHERE TO_CHAR(date, 'YYYY-MM') = %s GROUP BY model ORDER BY inp DESC",
                (current_month,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as out, SUM(cost_usd) as total"
                " FROM cost_logs WHERE strftime('%Y-%m', date) = ? GROUP BY model ORDER BY inp DESC",
                (current_month,),
            ).fetchall()

    if not rows:
        return "이번 달 사용 기록이 없습니다."

    pkce_rows = []
    api_rows = []
    for r in rows:
        name = _normalize_model(str(r["model"]))
        if name in _PKCE_MODELS:
            pkce_rows.append(r)
        else:
            api_rows.append(r)

    lines = [f"이번 달 사용량 ({current_month})", ""]

    if api_rows:
        api_total = sum(float(r["total"]) for r in api_rows)
        lines.append(f"[OpenAI API]  (합계: ${api_total:.4f})")
        for r in api_rows:
            inp = int(r["inp"])
            out = int(r["out"])
            cost = float(r["total"])
            name = _normalize_model(str(r["model"]))
            lines.append(f"- {name}: 입력 {inp / 1_000_000:.2f}M / 출력 {out / 1_000_000:.2f}M → ${cost:.4f}")
        lines.append("")

    if pkce_rows:
        lines.append("[ChatGPT Plus ($20/월 정액)]")
        for r in pkce_rows:
            inp = int(r["inp"])
            out = int(r["out"])
            name = _normalize_model(str(r["model"]))
            lines.append(f"- {name}: 입력 {inp / 1_000_000:.2f}M / 출력 {out / 1_000_000:.2f}M")

    return "\n".join(lines)
