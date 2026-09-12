from typing import Any, Dict, List
import numpy as np
from .alerts import build_alerts
from .metrics import calculate_metrics


def portfolio_risk(weights: Dict[str, float], return_series: Dict[str, List[float]]) -> Dict[str, Any]:
    codes = [c for c in weights if c in return_series]
    if not codes or min((len(return_series[c]) for c in codes), default=0) < 3:
        return {"status": "insufficient_data", "risk_level": None, "alerts": []}
    size = min(len(return_series[c]) for c in codes)
    matrix = np.asarray([return_series[c][-size:] for c in codes], dtype=float)
    w = np.asarray([weights[c] for c in codes], dtype=float)
    w = w / w.sum()
    cov = np.cov(matrix) if len(codes) > 1 else np.asarray([[np.var(matrix[0], ddof=1)]])
    variance = float(w @ cov @ w)
    vol = float(np.sqrt(max(variance, 0)) * np.sqrt(252))
    marginal = cov @ w
    contributions = w * marginal / variance if variance > 0 else np.zeros_like(w)
    portfolio_returns = w @ matrix
    equity = np.cumprod(1 + portfolio_returns)
    perf = calculate_metrics(equity.tolist())
    trailing = portfolio_returns[-30:]
    return_30d = float(np.prod(1 + trailing) - 1) if len(trailing) else None
    concentration = float(np.sum(w ** 2))
    score = round(min(100.0, vol / 0.45 * 70 + concentration * 30), 2)
    level = "high" if score >= 67 else ("medium" if score >= 34 else "low")
    main_idx = int(np.argmax(contributions))
    risk = {"status": "ok", "risk_level": level, "risk_score": score,
            "volatility": round(vol, 6), "concentration": round(concentration, 6),
            "max_drawdown": perf.get("max_drawdown"),
            "return_30d": round(return_30d, 6) if return_30d is not None else None,
            "downside_volatility": perf.get("downside_volatility"),
            "sharpe": perf.get("sharpe"), "sortino": perf.get("sortino"),
            "calmar": perf.get("calmar"),
            "main_risk_source": codes[main_idx],
            "risk_contribution": {c: round(float(v), 6) for c, v in zip(codes, contributions)}}
    risk["alerts"] = build_alerts(risk, concentration)
    return risk
