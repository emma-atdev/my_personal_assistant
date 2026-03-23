"""API 비용 추적 툴 — 모델별 토큰 사용량과 비용을 DB에 기록한다."""

from datetime import datetime

from storage.db import PH, get_conn

# 모델별 1토큰당 USD 비용
PRICING: dict[str, dict[str, float]] = {
    "gpt-5.2": {"input": 1.75 / 1_000_000, "output": 14.0 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.0 / 1_000_000},
}


def log_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """API 토큰 사용량을 기록한다 (내부 사용)."""
    pricing = PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    with get_conn() as con:
        con.execute(
            f"INSERT INTO cost_logs (model, input_tokens, output_tokens, cost_usd) VALUES ({PH}, {PH}, {PH}, {PH})",
            (model, input_tokens, output_tokens, round(cost, 6)),
        )


def get_cost_summary() -> str:
    """이번 달 API 비용 요약을 반환한다. 비용 확인이 필요할 때 사용."""
    current_month = datetime.now().strftime("%Y-%m")

    with get_conn() as con:
        if PH == "%s":
            rows = con.execute(
                "SELECT model, SUM(cost_usd) as total FROM cost_logs "
                "WHERE TO_CHAR(date, 'YYYY-MM') = %s GROUP BY model ORDER BY total DESC",
                (current_month,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT model, SUM(cost_usd) as total FROM cost_logs "
                "WHERE strftime('%Y-%m', date) = ? GROUP BY model ORDER BY total DESC",
                (current_month,),
            ).fetchall()

    if not rows:
        return "이번 달 비용 기록이 없습니다."

    total = sum(float(r["total"]) for r in rows)
    lines = [
        f"**이번 달 API 비용 ({current_month})**",
        f"총합: ${total:.4f}",
        "",
    ]
    for r in rows:
        lines.append(f"- {r['model']}: ${float(r['total']):.4f}")

    return "\n".join(lines)
