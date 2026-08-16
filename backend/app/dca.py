"""
定投回测模块
模拟按周/月定投某基金的历史收益，对标市面「定投计算器 / 定投回测」：
- 普通定投（normal）：每期固定金额买入
- 智能定投（value_avg，价值平均）：目标市值每期增长固定额，差额自动买入/卖出
输出：累计本金、累计份额、期末市值、总收益率、IRR（内部收益率）、每期现金流，
以及供图表绘制的 市值 / 成本 / 净值 序列。
"""
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np

from .schemas import NavPoint


def _xirr(dates: List[datetime], amounts: List[float]) -> float:
    """现金加权利率（IRR）。amounts 中投入为负、赎回/期末为正。
    以天为单位，二分法求解 sum(amount / (1+rate)^(days/365)) = 0。"""
    if len(amounts) < 2:
        return 0.0
    t0 = dates[0]
    days = [(d - t0).days for d in dates]
    # 到期日必须为正现金流（清算），否则无意义
    def npv(rate):
        return sum(a / (1.0 + rate) ** (dd / 365.0) for a, dd in zip(amounts, days))
    lo, hi = -0.99, 20.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        # 区间内无符号变化，返回粗略年化（期末/本金）
        return 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def _pick_invest_indices(n: int, freq: str) -> List[int]:
    """在长度为 n 的交易日序列中选定理财定投时点。"""
    if freq == "weekly":
        step = max(1, round(n / max(1, int(n / 5))))  # 约每 5 个交易日（一周）
        return list(range(0, n, max(1, step)))
    # monthly：取每月首个交易日
    idxs: List[int] = []
    last_month = None
    # 这里没有显式日期，用「分段」近似：把序列均分为若干月（≈21 交易日/月）
    per_month = max(1, round(n / max(1, int(n / 21))))
    for i in range(0, n, max(1, per_month)):
        idxs.append(i)
    return idxs


def run(points: List[NavPoint], amount: float = 1000.0, freq: str = "monthly",
        strategy: str = "normal", fee_bps: float = 15.0,
        periods_per_year: int = 252) -> Dict[str, Any]:
    """
    定投回测。
    - amount: 每期基准金额（元）
    - freq: monthly / weekly
    - strategy: normal（普通定投）/ value_avg（价值平均智能定投）
    - fee_bps: 单边申购费率（基点，15 = 0.15%）
    返回定投明细与绩效。
    """
    navs = [p.nav for p in points]
    n = len(navs)
    if n < 10:
        return {"error": "历史数据不足，无法定投回测"}

    fee = fee_bps / 10000.0
    idxs = _pick_invest_indices(n, freq)
    if len(idxs) < 2:
        idxs = list(range(0, n, max(1, n // 2)))

    shares = 0.0
    principal = 0.0          # 累计净投入（买入为正流出，卖出为正流入，principal 取净投入）
    gross_in = 0.0           # 累计买入金额
    redeemed = 0.0           # 累计赎回金额
    invest_cf = []           # 每期现金流（负=买入，正=赎回）
    invest_amt = []          # 每期实际交易金额（正=买入，负=赎回）
    cost_series = []         # 累计净投入
    value_series = []        # 组合市值
    nav_series = []
    date_series = []
    value_target = 0.0       # 价值平均目标市值

    for k, i in enumerate(idxs, start=1):
        nav = navs[i]
        date = points[i].date
        port_value = shares * nav
        if strategy == "value_avg":
            value_target += amount
            need = value_target - port_value   # 需补足到目标市值的金额
            if need >= 0:
                buy = need * (1 - fee)
                shares += buy / nav
                principal += buy
                gross_in += buy
                invest_amt.append(round(buy, 2))
                invest_cf.append(-round(buy, 2))
            else:
                sell = min(-need, port_value) * (1 - fee)
                shares -= sell / nav
                principal -= sell
                redeemed += sell
                invest_amt.append(round(-sell, 2))
                invest_cf.append(round(sell, 2))
        else:
            buy = amount * (1 - fee)
            shares += buy / nav
            principal += buy
            gross_in += buy
            invest_amt.append(round(buy, 2))
            invest_cf.append(-round(buy, 2))

        value_series.append(round(shares * nav, 2))
        cost_series.append(round(principal, 2))
        nav_series.append(round(nav, 4))
        date_series.append(date)

    final_nav = navs[-1]
    final_value = shares * final_nav
    total_return = (final_value - principal) / principal * 100 if principal > 0 else 0.0

    # XIRR：每期现金流 + 期末清算
    try:
        dts = [datetime.strptime(d, "%Y-%m-%d") for d in date_series]
        cf = list(invest_cf) + [round(final_value, 2)]
        dts = dts + [dts[-1]]
        xirr = _xirr(dts, cf)
    except Exception:
        xirr = 0.0

    strategy_name = "普通定投" if strategy != "value_avg" else "智能定投（价值平均）"

    return {
        "strategy": strategy,
        "strategy_name": strategy_name,
        "freq": freq,
        "amount": amount,
        "fee_bps": fee_bps,
        "periods": len(idxs),
        "first_date": date_series[0] if date_series else None,
        "last_date": date_series[-1] if date_series else None,
        "shares": round(shares, 2),
        "principal": round(principal, 2),
        "gross_invested": round(gross_in, 2),
        "redeemed": round(redeemed, 2),
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return, 2),
        "xirr_pct": round(xirr * 100, 2),
        "dates": date_series,
        "invest_amt": invest_amt,
        "cost_series": cost_series,
        "value_series": value_series,
        "nav_series": nav_series,
    }
