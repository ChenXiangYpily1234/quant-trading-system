"""
组合再平衡 / 资产配置模块
对标市面「组合回测 / 资产配置」能力（如蛋卷组合、且慢、智投星）：
- equal（等权）：所有持仓权重相同
- risk_parity（风险平价近似）：权重与年化波动率成反比，波动越低配得越多
- signal（信号加权）：按预测方向+置信度倾斜，看多加仓、看平/看减归零
给定各持仓的市值、年化波动率、信号，输出目标权重与建议调仓金额。
"""
from typing import Dict, Any, List


def target_weights(method: str,
                    values: Dict[str, float],
                    vols: Dict[str, float],
                    signals: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """
    method: equal | risk_parity | signal
    values: code -> 当前市值
    vols:   code -> 年化波动率（小数，如 0.2 表示 20%）
    signals:code -> {"direction": up/down/flat, "confidence": 0~1}
    返回 code -> 目标权重（合计 1.0）
    """
    codes = list(values.keys())
    if not codes:
        return {}
    if method == "risk_parity":
        inv = {c: 1.0 / max(vols.get(c, 0.0), 1e-4) for c in codes}
        s = sum(inv.values())
        return {c: inv[c] / s for c in codes}
    if method == "signal":
        raw: Dict[str, float] = {}
        for c in codes:
            sig = signals.get(c, {})
            if sig.get("direction") == "up":
                raw[c] = max(0.0, float(sig.get("confidence", 0.0) or 0.0))
            else:
                raw[c] = 0.0
        s = sum(raw.values())
        if s <= 0:
            # 全空信号时退化为等权
            return {c: 1.0 / len(codes) for c in codes}
        return {c: raw[c] / s for c in codes}
    # equal
    return {c: 1.0 / len(codes) for c in codes}


def suggest(method: str,
             navs: Dict[str, float],
             vols: Dict[str, float],
             signals: Dict[str, Dict[str, Any]],
             prices: Dict[str, float],
             names: Dict[str, str] = None) -> Dict[str, Any]:
    """
    生成再平衡建议明细。
    navs:   code -> 当前市值
    prices: code -> 最新净值（用于换算份额）
    names:  code -> 基金名称（展示用）
    返回 {method, total, positions[], note}
    """
    names = names or {}
    total = sum(navs.values())
    weights = target_weights(method, navs, vols, signals)
    positions: List[Dict[str, Any]] = []
    for c in navs:
        cur = navs[c]
        w = weights.get(c, 0.0)
        tgt = w * total
        delta = tgt - cur
        price = prices.get(c) or 0.0
        shares_delta = round(delta / price, 2) if price > 0 else 0.0
        if abs(delta) < max(total * 0.005, 1.0):
            action = "持有"
        elif delta > 0:
            action = "加仓"
        else:
            action = "减仓"
        positions.append({
            "code": c,
            "name": names.get(c, c),
            "current_value": round(cur, 2),
            "current_weight": round(cur / total * 100, 2) if total else 0.0,
            "target_weight": round(w * 100, 2),
            "target_value": round(tgt, 2),
            "delta_value": round(delta, 2),
            "delta_pct": round(delta / total * 100, 2) if total else 0.0,
            "suggested_shares": shares_delta,
            "action": action,
        })
    positions.sort(key=lambda x: x["delta_value"], reverse=True)
    note = {
        "equal": "等权配置：每只持仓目标权重相同，最简单稳健。",
        "risk_parity": "风险平价：权重与年化波动率成反比，波动越低配得越多，使组合波动更均衡。",
        "signal": "信号加权：按预测方向+置信度倾斜，看多加仓、看平/看减归零（无看多信号时退化为等权）。",
    }.get(method, "")
    return {"method": method, "total": round(total, 2),
            "positions": positions, "note": note}
