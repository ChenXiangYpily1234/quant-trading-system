"""
技术指标模块
基于日频单位净值序列计算 MA / EMA / MACD / BOLL / KDJ / RSI 序列，
供前端主图叠加与副图（MACD / RSI / KDJ）绘制。
说明：基金净值无最高/最低价，KDJ 用 N 日净值滚动最高/最低近似（业内常用处理）。
"""
from typing import List, Optional, Dict, Any

import numpy as np


def _r(v, n=4):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return round(float(v), n)


def ma(values: List[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(_r(np.mean(values[i + 1 - window:i + 1])))
    return out


def ema(values: List[float], window: int) -> List[Optional[float]]:
    if not values:
        return []
    k = 2 / (window + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return [_r(x) for x in out]


def macd(values: List[float], fast=12, slow=26, signal=9) -> Dict[str, List[Optional[float]]]:
    if len(values) < 2:
        return {"dif": [], "dea": [], "hist": []}
    ef = ema(values, fast)
    es = ema(values, slow)
    dif = [_r((a or 0) - (b or 0)) for a, b in zip(ef, es)]
    dea = ema([d or 0 for d in dif], signal)
    hist = [_r(2 * ((d or 0) - (s or 0))) for d, s in zip(dif, dea)]
    return {"dif": dif, "dea": dea, "hist": hist}


def boll(values: List[float], window=20, mult=2.0) -> Dict[str, List[Optional[float]]]:
    mid = ma(values, window)
    up: List[Optional[float]] = []
    low: List[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            up.append(None)
            low.append(None)
        else:
            seg = values[i + 1 - window:i + 1]
            sd = float(np.std(seg))
            m = mid[i] or 0
            up.append(_r(m + mult * sd))
            low.append(_r(m - mult * sd))
    return {"mid": mid, "upper": up, "lower": low}


def kdj(values: List[float], n=9, m1=3, m2=3) -> Dict[str, List[Optional[float]]]:
    k_list: List[Optional[float]] = []
    d_list: List[Optional[float]] = []
    j_list: List[Optional[float]] = []
    k_prev, d_prev = 50.0, 50.0
    for i in range(len(values)):
        if i + 1 < n:
            k_list.append(None)
            d_list.append(None)
            j_list.append(None)
            continue
        seg = values[i + 1 - n:i + 1]
        hi, lo = max(seg), min(seg)
        rsv = 50.0 if hi == lo else (values[i] - lo) / (hi - lo) * 100
        k_cur = (m1 - 1) / m1 * k_prev + 1 / m1 * rsv
        d_cur = (m2 - 1) / m2 * d_prev + 1 / m2 * k_cur
        k_prev, d_prev = k_cur, d_cur
        k_list.append(_r(k_cur, 2))
        d_list.append(_r(d_cur, 2))
        j_list.append(_r(3 * k_cur - 2 * d_cur, 2))
    return {"k": k_list, "d": d_list, "j": j_list}


def rsi_series(values: List[float], window=14) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    if len(values) < 2:
        return [None] * len(values)
    rets = [0.0] + [(values[i] / values[i - 1] - 1) if values[i - 1] else 0.0
                    for i in range(1, len(values))]
    for i in range(len(values)):
        if i + 1 <= window:
            out.append(None)
            continue
        seg = rets[i + 1 - window:i + 1]
        gains = [max(r, 0) for r in seg]
        losses = [max(-r, 0) for r in seg]
        ag, al = float(np.mean(gains)), float(np.mean(losses))
        out.append(_r(100.0 if al == 0 else 100 - 100 / (1 + ag / al), 2))
    return out


def compute_all(values: List[float]) -> Dict[str, Any]:
    """一次性计算所有指标序列。"""
    return {
        "ma5": ma(values, 5),
        "ma10": ma(values, 10),
        "ma20": ma(values, 20),
        "ma60": ma(values, 60),
        "boll": boll(values, 20, 2.0),
        "macd": macd(values),
        "kdj": kdj(values),
        "rsi": rsi_series(values, 14),
    }


def perf_stats(values: List[float], periods_per_year: int = 252, risk_free: float = 0.0) -> Dict[str, Any]:
    """区间业绩统计：累计收益 / 年化 / 波动 / 最大回撤 / 夏普 / 索提诺 / 卡玛 / 胜率。
    - 夏普 = (年化收益 - 无风险) / 年化波动
    - 索提诺 = (年化收益 - 无风险) / 年化下行波动（仅惩罚下跌）
    - 卡玛 = 年化收益 / 最大回撤
    """
    if len(values) < 2:
        return {"total_return": 0, "annual_return": 0, "volatility": 0,
                "max_drawdown": 0, "sharpe": 0, "sortino": 0, "calmar": 0,
                "downside_dev": 0, "win_rate": 0, "days": len(values)}
    arr = np.array(values, dtype=float)
    rets = arr[1:] / arr[:-1] - 1
    total = arr[-1] / arr[0] - 1
    n = len(arr) - 1
    annual = (1 + total) ** (periods_per_year / max(n, 1)) - 1
    vol = float(np.std(rets)) * np.sqrt(periods_per_year)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / peak
    mdd = float(dd.min())
    std_ret = float(np.std(rets))
    sharpe = float((np.mean(rets) * periods_per_year - risk_free) / (std_ret * np.sqrt(periods_per_year))) if std_ret > 0 else 0.0
    # 下行波动：仅低于 0 的收益
    down = rets[rets < 0]
    downside_dev = float(np.std(down)) * np.sqrt(periods_per_year) if down.size > 0 else 0.0
    sortino = float((annual - risk_free) / downside_dev) if downside_dev > 0 else (0.0 if annual <= 0 else 9.99)
    calmar = float(annual / abs(mdd)) if mdd < 0 else 0.0
    win = float((rets > 0).sum() / len(rets))
    return {
        "total_return": round(total * 100, 2),
        "annual_return": round(annual * 100, 2),
        "volatility": round(vol * 100, 2),
        "max_drawdown": round(mdd * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "downside_dev": round(downside_dev * 100, 2),
        "win_rate": round(win * 100, 1),
        "days": len(arr),
    }


def valuation_temperature(values: List[float], ma_window: int = 60) -> Dict[str, Any]:
    """净值估值温度（0-100，参考「市场温度」思路）：
    以 NAV 相对其长期均线的偏离比例序列，当前偏离在历史分布中的百分位即为温度。
    <30 低估(冷) / 30~70 适中(温) / >70 高估(热)。
    注：基金无公开 PE，此处用「净值相对长期均线」的偏离度作为估值冷暖代理。
    """
    if len(values) < 30:
        return {"temp": 50.0, "label": "适中", "nav_pct_rank": 50.0, "ma_ratio": None}
    mw = min(ma_window, max(20, len(values) // 3))
    mas = ma(values, mw)
    ratio = [values[i] / mas[i] for i in range(len(values)) if mas[i]]
    if len(ratio) < 5:
        return {"temp": 50.0, "label": "适中", "nav_pct_rank": 50.0, "ma_ratio": None}
    cur = ratio[-1]
    below = sum(1 for r in ratio if r <= cur)
    temp = round(below / len(ratio) * 100, 1)
    label = "低估" if temp < 30 else ("高估" if temp > 70 else "适中")
    nav_below = sum(1 for v in values if v <= values[-1])
    nav_pct = round(nav_below / len(values) * 100, 1)
    return {"temp": temp, "label": label, "nav_pct_rank": nav_pct, "ma_ratio": round(cur, 3)}
