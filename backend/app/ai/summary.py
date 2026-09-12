from typing import Any, Dict, List


def dashboard_summary(performance: Dict[str, Any], risk: Dict[str, Any], changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    if risk.get("status") != "ok":
        text = "组合风险数据暂不完整；真实行情恢复后将自动更新。"
    else:
        level = {"low": "较低", "medium": "中等", "high": "较高"}.get(risk.get("risk_level"), "未知")
        source = risk.get("main_risk_source") or "暂无"
        text = f"当前组合风险{level}，主要风险来源为 {source}。"
    if changes:
        text += f" 今日有 {len(changes)} 项变化值得进一步查看。"
    return {"text": text, "engine": "deterministic_fallback", "is_advice": False}
