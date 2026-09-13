from datetime import date, timedelta

from backend.app.backtest import run
from backend.app.research.red_team import audit_backtest
from backend.app.schemas import NavPoint


def _points():
    return [NavPoint(date=(date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                     nav=1 + i * 0.002) for i in range(50)]


def test_red_team_detects_future_position_trace():
    points = _points()
    result = run(points, strategy="momentum", short=5)
    result["position"] = result["position"][1:] + [result["position"][-1]]
    report = audit_backtest(points, result)
    assert report.verdict == "FAIL"
    assert next(c for c in report.checks if c.code == "execution_timing").status == "FAIL"


def test_red_team_never_calls_missing_oos_a_pass():
    points = _points()
    result = run(points, strategy="momentum", short=5)
    report = audit_backtest(points, result)
    assert report.verdict == "WARNING"
    assert next(c for c in report.checks if c.code == "out_of_sample").status == "WARNING"
