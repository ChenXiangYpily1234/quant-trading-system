from typing import Any, Dict, List


def build_alerts(risk: Dict[str, Any], concentration: float = 0.0) -> List[Dict[str, str]]:
    alerts = []
    if risk.get("max_drawdown", 0) <= -0.10:
        alerts.append({"level": "high", "code": "DRAWDOWN", "message": "历史最大回撤超过 10%"})
    if risk.get("volatility", 0) >= 0.30:
        alerts.append({"level": "high", "code": "VOLATILITY", "message": "年化波动率处于高位"})
    if concentration >= 0.50:
        alerts.append({"level": "medium", "code": "CONCENTRATION", "message": "单一基金占比超过 50%"})
    return alerts
