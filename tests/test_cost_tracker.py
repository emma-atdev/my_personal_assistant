"""tools/cost_tracker.py 단위 테스트."""

from tools.cost_tracker import get_cost_summary, log_usage


def test_cost_summary_empty() -> None:
    result = get_cost_summary()
    assert "없습니다" in result


def test_log_and_get_cost_summary() -> None:
    log_usage("gpt-4o-mini", input_tokens=1000, output_tokens=500)
    result = get_cost_summary()
    assert "gpt-4o-mini" in result
    assert "$" in result


def test_cost_calculation() -> None:
    # gpt-4o-mini: input $0.15/1M, output $0.60/1M
    # 1000 input + 500 output = $0.00015 + $0.0003 = $0.00045
    log_usage("gpt-4o-mini", input_tokens=1000, output_tokens=500)
    result = get_cost_summary()
    assert "0.000450" in result or "0.0004" in result


def test_multiple_models() -> None:
    log_usage("gpt-4o-mini", input_tokens=100, output_tokens=100)
    log_usage("gpt-4o", input_tokens=100, output_tokens=100)
    result = get_cost_summary()
    assert "gpt-4o-mini" in result
    assert "gpt-4o" in result
