from typing import Any, Dict, List
import numpy as np


def calculate_metrics(navs: List[float], risk_free_rate: float = 0.0) -> Dict[str, Any]:
    if len(navs) < 3 or any(v <= 0 for v in navs):
        return {"status": "insufficient_data"}
    arr = np.asarray(navs, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    annual_return = float((arr[-1] / arr[0]) ** (252 / max(1, len(rets))) - 1)
    volatility = float(np.std(rets, ddof=1) * np.sqrt(252))
    downside = rets[rets < 0]
    downside_vol = float(np.std(downside, ddof=1) * np.sqrt(252)) if len(downside) > 1 else 0.0
    peaks = np.maximum.accumulate(arr)
    max_drawdown = float(np.min(arr / peaks - 1))
    excess = annual_return - risk_free_rate
    return {
        "status": "ok", "annual_return": round(annual_return, 6),
        "volatility": round(volatility, 6), "downside_volatility": round(downside_vol, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(excess / volatility, 6) if volatility else None,
        "sortino": round(excess / downside_vol, 6) if downside_vol else None,
        "calmar": round(annual_return / abs(max_drawdown), 6) if max_drawdown else None,
    }
