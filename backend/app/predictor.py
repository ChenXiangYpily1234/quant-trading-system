"""
预测模块（统计法）
基于历史净值计算技术指标，并结合新闻情感，给出短期走势预测与可视化所需序列。
大模型决策见 llm.py；本模块提供客观量化信号。
"""
import math
import time
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from . import config, fund_data
from .schemas import NavPoint


def _seed(code: str) -> int:
    return int(hashlib.md5(code.encode()).hexdigest(), 16) % (2 ** 31)


def moving_average(values: List[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            seg = values[i + 1 - window: i + 1]
            out.append(round(float(np.mean(seg)), 4))
    return out


def compute_indicators(points: List[NavPoint]) -> Dict[str, Any]:
    navs = [p.nav for p in points]
    n = len(navs)
    ma5 = moving_average(navs, 5)
    ma20 = moving_average(navs, 20)
    rets = [0.0] + [(navs[i] / navs[i - 1] - 1) for i in range(1, n)] if n > 1 else [0.0]
    momentum5 = (navs[-1] / navs[-6] - 1) if n >= 6 else (navs[-1] / navs[0] - 1 if n else 0)
    momentum20 = (navs[-1] / navs[-21] - 1) if n >= 21 else (navs[-1] / navs[0] - 1 if n else 0)
    vol = float(np.std(rets[1:])) if n > 2 else 0.0
    # RSI(14)
    rsi = 50.0
    if n >= 15:
        gains = [max(r, 0) for r in rets[1:][-14:]]
        losses = [max(-r, 0) for r in rets[1:][-14:]]
        ag, al = np.mean(gains), np.mean(losses)
        rsi = 100 - (100 / (1 + (ag / al if al else 999))) if al else 100.0
    return {
        "ma5": ma5, "ma20": ma20,
        "momentum5": round(momentum5 * 100, 2),
        "momentum20": round(momentum20 * 100, 2),
        "volatility": round(vol * 100, 2),
        "rsi": round(rsi, 1),
        "latest_nav": navs[-1] if navs else None,
        "prev_nav": navs[-2] if n >= 2 else None,
    }


def aggregate_news_sentiment(news_items) -> Dict[str, Any]:
    if not news_items:
        return {"avg_sentiment": 0.0, "pos": 0, "neg": 0, "count": 0}
    top = [n for n in news_items if n.relevance > 0][:10]
    if not top:
        top = news_items[:10]
    sents = [n.sentiment for n in top]
    pos = sum(1 for s in sents if s > 0.1)
    neg = sum(1 for s in sents if s < -0.1)
    avg = float(np.mean(sents)) if sents else 0.0
    return {"avg_sentiment": round(avg, 2), "pos": pos, "neg": neg, "count": len(top)}


def predict(code: str, points: List[NavPoint], sentiment: Dict[str, Any]) -> Dict[str, Any]:
    ind = compute_indicators(points)
    latest = ind["latest_nav"]
    # 多空信号合成
    signals = []
    if ind["momentum5"] > 0:
        signals.append(1)
    else:
        signals.append(-1)
    if ind["momentum20"] > 0:
        signals.append(1)
    else:
        signals.append(-1)
    # 价格位于均线之上偏多
    if ind["ma5"] and ind["ma5"][-1] and latest > ind["ma5"][-1]:
        signals.append(1)
    elif ind["ma5"] and ind["ma5"][-1]:
        signals.append(-1)
    # 新闻情感
    ns = sentiment.get("avg_sentiment", 0.0)
    score = float(np.mean(signals)) if signals else 0.0
    combined = 0.7 * score + 0.3 * ns  # -1 ~ 1

    direction = "up" if combined > 0.15 else ("down" if combined < -0.15 else "flat")

    # 预期日收益：动量衰减 + 新闻微调
    expected_daily = (ind["momentum5"] / 100.0) * 0.25 + ns * 0.003
    expected_daily = max(min(expected_daily, 0.03), -0.03)

    # 置信度：信号一致性强 + 动量显著 + 新闻充足
    consistency = abs(score)
    conf = 0.45 + 0.25 * consistency + 0.1 * min(abs(ind["momentum5"]) / 5, 1) + 0.1 * min(sentiment.get("count", 0) / 8, 1)
    conf = round(min(max(conf, 0.4), 0.9), 2)

    # 未来序列（用于图表虚线 + 置信带）
    rng = np.random.default_rng(_seed(code))
    future_dates, future_nav, upper, lower = [], [], [], []
    cur = latest
    vol = max(ind["volatility"] / 100.0, 0.008)
    base = time.time()
    for i in range(1, config.PREDICT_DAYS + 1):
        cur = cur * (1 + expected_daily + rng.normal(0, vol * 0.3))
        d = time.strftime("%Y-%m-%d", time.localtime(base + i * 86400))
        future_dates.append(d)
        future_nav.append(round(cur, 4))
        upper.append(round(cur * (1 + vol * 0.8), 4))
        lower.append(round(cur * (1 - vol * 0.8), 4))

    predicted_change = round((future_nav[-1] / latest - 1) * 100, 2) if latest else 0.0

    rationale = (
        f"近5日动量{ind['momentum5']:+.2f}%，近20日{ind['momentum20']:+.2f}%；"
        f"RSI={ind['rsi']}；日波动{ind['volatility']:.2f}%；"
        f"相关新闻情感{'偏多' if ns>0.1 else ('偏空' if ns<-0.1 else '中性')}({ns:+.2f})。"
    )

    return {
        "direction": direction,
        "predicted_nav": future_nav[-1],
        "predicted_change_pct": predicted_change,
        "confidence": conf,
        "horizon_days": config.PREDICT_DAYS,
        "expected_daily_return_pct": round(expected_daily * 100, 3),
        "indicators": ind,
        "future_dates": future_dates,
        "future_nav": future_nav,
        "future_upper": upper,
        "future_lower": lower,
        "rationale": rationale,
    }
