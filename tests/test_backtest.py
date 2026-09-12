from backend.app.backtest import run
from backend.app.schemas import NavPoint


def points(values):
    return [NavPoint(date=f"2026-01-{i+1:02d}", nav=value) for i, value in enumerate(values)]


def test_signal_executes_on_next_day():
    result = run(points([1, 1, 1, 1, 1, 2, 2, 2]), strategy="momentum", short=2, fee_bps=0)
    first_buy = next(mark for mark in result["marks"] if mark["type"] == "buy")
    assert first_buy["date"] == "2026-01-07"


def test_costs_reduce_net_return_and_benchmark_is_reported():
    data = points([1, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06])
    result = run(data, strategy="buy_hold", fee_bps=20)
    assert result["net_return"] < result["gross_return"]
    assert result["benchmark_return"] == result["benchmark_stats"]["total_return"]
    assert result["excess_return"] == result["stats"]["excess_return"]
