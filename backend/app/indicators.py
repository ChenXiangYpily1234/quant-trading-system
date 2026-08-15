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


def perf_stats(values: List[float], periods_per_year: int = 252) -> Dict[str, Any]:
    """区间业绩统计：累计收益 / 年化 / 波动 / 最大回撤 / 夏普 / 胜率。"""
    if len(values) < 2:
        return {"total_return": 0, "annual_return": 0, "volatility": 0,
                "max_drawdown": 0, "sharpe": 0, "win_rate": 0, "days": len(values)}
    arr = np.array(values, dtype=float)
    rets = arr[1:] / arr[:-1] - 1
    total = arr[-1] / arr[0] - 1
    n = len(arr) - 1
    annual = (1 + total) ** (periods_per_year / max(n, 1)) - 1
    vol = float(np.std(rets)) * np.sqrt(periods_per_year)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / peak
    mdd = float(dd.min())
    sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(periods_per_year)) if np.std(rets) > 0 else 0.0
    win = float((rets > 0).sum() / len(rets))
    return {
        "total_return": round(total * 100, 2),
        "annual_return": round(annual * 100, 2),
        "volatility": round(vol * 100, 2),
        "max_drawdown": round(mdd * 100, 2),
        "sharpe": round(sharpe, 2),
        "win_rate": round(win * 100, 1),
        "days": len(arr),
    }
