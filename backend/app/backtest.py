"""
策略回测模块
在真实历史净值上回测「双均线」与「动量」策略，输出资金曲线、交易明细与绩效统计，
并与「买入持有」基准对比。参数（均线周期、手续费、区间）由前端交互调节。
"""
from typing import List, Dict, Any

import numpy as np

from . import indicators
from .schemas import NavPoint


def _signals_ma(navs: List[float], short: int, long: int) -> List[int]:
    """双均线：短均线上穿长均线 -> 持有(1)，下穿 -> 空仓(0)。"""
    ms = indicators.ma(navs, short)
    ml = indicators.ma(navs, long)
    pos = [0] * len(navs)
    cur = 0
    for i in range(len(navs)):
        s, l = ms[i], ml[i]
        if s is None or l is None:
            pos[i] = 0
            continue
        if s > l:
            cur = 1
        elif s < l:
            cur = 0
        pos[i] = cur
    return pos


def _signals_momentum(navs: List[float], window: int) -> List[int]:
    """动量：过去 window 日收益为正则持有。"""
    pos = [0] * len(navs)
    for i in range(len(navs)):
        if i < window:
            continue
        pos[i] = 1 if navs[i] > navs[i - window] else 0
    return pos


def run(points: List[NavPoint], strategy: str = "ma_cross", short: int = 5,
        long: int = 20, fee_bps: float = 15.0) -> Dict[str, Any]:
    """
    执行回测。
    - strategy: ma_cross（双均线） / momentum（动量） / buy_hold（买入持有）
    - fee_bps: 单边费率（基点，15 = 0.15%），买卖各扣一次
    信号在 T 日产生，T+1 日按净值成交（避免未来函数）。
    """
    dates = [p.date for p in points]
    navs = [p.nav for p in points]
    n = len(navs)
    if n < 5:
        return {"error": "历史数据不足，无法回测"}

    short = max(2, min(int(short), 120))
    long = max(short + 1, min(int(long), 250))

    if strategy == "momentum":
        raw_pos = _signals_momentum(navs, short)
        strategy_name = f"动量策略（{short}日）"
    elif strategy == "buy_hold":
        raw_pos = [1] * n
        strategy_name = "买入持有"
    else:
        raw_pos = _signals_ma(navs, short, long)
        strategy_name = f"双均线策略（MA{short}/MA{long}）"

    fee = fee_bps / 10000.0
    equity = [1.0]
    pos_series = [0]
    trades: List[Dict[str, Any]] = []
    holding = 0
    entry_price = None
    entry_date = None

    for i in range(1, n):
        target = raw_pos[i - 1]          # 用前一日信号，今日执行
        ret = navs[i] / navs[i - 1] - 1
        eq = equity[-1] * (1 + ret * holding)

        if target != holding:
            eq *= (1 - fee)
            if target == 1:
                holding = 1
                entry_price = navs[i]
                entry_date = dates[i]
            else:
                holding = 0
                if entry_price:
                    pnl = navs[i] / entry_price - 1
                    trades.append({
                        "entry_date": entry_date, "entry_nav": round(entry_price, 4),
                        "exit_date": dates[i], "exit_nav": round(navs[i], 4),
                        "return_pct": round(pnl * 100, 2),
                        "win": pnl > 0,
                    })
                entry_price, entry_date = None, None

        equity.append(round(eq, 6))
        pos_series.append(holding)

    # 未平仓的最后一笔
    open_trade = None
    if holding == 1 and entry_price:
        pnl = navs[-1] / entry_price - 1
        open_trade = {
            "entry_date": entry_date, "entry_nav": round(entry_price, 4),
            "exit_date": "持仓中", "exit_nav": round(navs[-1], 4),
            "return_pct": round(pnl * 100, 2), "win": pnl > 0,
        }

    benchmark = [round(v / navs[0], 6) for v in navs]

    st = indicators.perf_stats(equity)
    bm = indicators.perf_stats(benchmark)
    closed = trades
    wins = sum(1 for t in closed if t["win"])
    trade_win_rate = round(wins / len(closed) * 100, 1) if closed else 0.0

    # 买卖标记点（供图表 markPoint）
    marks = []
    for i in range(1, n):
        if pos_series[i] != pos_series[i - 1]:
            marks.append({"date": dates[i], "nav": round(navs[i], 4),
                          "type": "buy" if pos_series[i] == 1 else "sell"})

    return {
        "strategy": strategy,
        "strategy_name": strategy_name,
        "params": {"short": short, "long": long, "fee_bps": fee_bps},
        "dates": dates,
        "equity": equity,
        "benchmark": benchmark,
        "position": pos_series,
        "marks": marks,
        "trades": (closed + ([open_trade] if open_trade else []))[-30:],
        "stats": {
            **st,
            "trade_count": len(closed) + (1 if open_trade else 0),
            "trade_win_rate": trade_win_rate,
            "excess_return": round(st["total_return"] - bm["total_return"], 2),
            "holding_ratio": round(sum(pos_series) / len(pos_series) * 100, 1),
        },
        "benchmark_stats": bm,
    }
