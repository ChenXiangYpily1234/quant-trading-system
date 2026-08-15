"""
持仓管理（持久化）
记录每只基金的持有份额与成本净值，结合最新净值计算市值、盈亏、权重，
并汇总组合层面的建议分布（加仓/减仓/持有各占多少市值）。
"""
from typing import List, Dict, Any, Optional

from . import store

FILE = "holdings.json"


def list_all() -> List[Dict]:
    data = store.load(FILE, [])
    return data if isinstance(data, list) else []


def upsert(code: str, shares: float, cost_nav: float, name: str = "") -> Dict:
    if not code:
        raise ValueError("基金代码不能为空")
    shares = float(shares)
    cost_nav = float(cost_nav)
    if shares <= 0 or cost_nav <= 0:
        raise ValueError("份额与成本净值必须大于 0")
    data = list_all()
    for h in data:
        if h["code"] == code:
            h["shares"] = shares
            h["cost_nav"] = cost_nav
            if name:
                h["name"] = name
            store.save(FILE, data)
            return h
    item = {"code": code, "name": name, "shares": shares, "cost_nav": cost_nav}
    data.append(item)
    store.save(FILE, data)
    return item


def remove(code: str) -> bool:
    data = list_all()
    left = [h for h in data if h["code"] != code]
    if len(left) == len(data):
        return False
    store.save(FILE, left)
    return True


def compute(nav_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    nav_map: code -> {"name":.., "nav":.., "day_change_pct":.., "advice":.., "direction":..}
    返回持仓明细 + 组合汇总。
    """
    holdings = list_all()
    rows: List[Dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        info = nav_map.get(h["code"], {})
        nav = info.get("nav")
        name = h.get("name") or info.get("name") or h["code"]
        shares = float(h["shares"])
        cost_nav = float(h["cost_nav"])
        cost = shares * cost_nav
        value = shares * nav if nav else None
        pnl = (value - cost) if value is not None else None
        rows.append({
            "code": h["code"],
            "name": name,
            "shares": round(shares, 2),
            "cost_nav": round(cost_nav, 4),
            "latest_nav": round(nav, 4) if nav else None,
            "cost": round(cost, 2),
            "value": round(value, 2) if value is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round((nav / cost_nav - 1) * 100, 2) if nav else None,
            "day_change_pct": info.get("day_change_pct"),
            "day_pnl": round(shares * nav * (info.get("day_change_pct") or 0) / 100, 2) if nav else None,
            "advice": info.get("advice"),
            "direction": info.get("direction"),
        })
        total_cost += cost
        if value is not None:
            total_value += value

    for r in rows:
        r["weight"] = round(r["value"] / total_value * 100, 2) if (r["value"] and total_value) else 0.0

    advice_mix: Dict[str, float] = {}
    for r in rows:
        adv = r.get("advice") or "未评估"
        advice_mix[adv] = round(advice_mix.get(adv, 0.0) + (r.get("weight") or 0.0), 2)

    total_pnl = total_value - total_cost if holdings else 0.0
    day_pnl = sum((r.get("day_pnl") or 0) for r in rows)

    rows.sort(key=lambda x: (x.get("value") or 0), reverse=True)

    return {
        "positions": rows,
        "summary": {
            "count": len(rows),
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost else 0.0,
            "day_pnl": round(day_pnl, 2),
            "day_pnl_pct": round(day_pnl / total_value * 100, 2) if total_value else 0.0,
            "advice_mix": advice_mix,
        },
    }
