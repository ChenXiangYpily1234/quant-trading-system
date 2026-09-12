import pytest
from backend.app.risk.metrics import calculate_metrics
from backend.app.risk.portfolio import portfolio_risk


def test_drawdown_and_ratios_are_calculated():
    result = calculate_metrics([1.0, 1.1, 0.88, 0.99])
    assert result["status"] == "ok"
    assert result["max_drawdown"] == pytest.approx(-0.2)
    assert result["volatility"] > 0


def test_portfolio_concentration_and_contribution():
    result = portfolio_risk({"A": 0.75, "B": 0.25},
                            {"A": [0.01, -0.01, 0.02], "B": [0.005, 0.0, -0.005]})
    assert result["status"] == "ok"
    assert result["concentration"] == pytest.approx(0.625)
    assert set(result["risk_contribution"]) == {"A", "B"}
