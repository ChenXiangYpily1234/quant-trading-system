from typing import Iterable, List
from .. import config
from ..data.provenance import permits_research
from ..features import momentum, sentiment, trend, volatility
from .schemas import SignalResult


def compute_signal(navs: List[float], sentiment_values: Iterable[float], data_source: str) -> SignalResult:
    if not permits_research(data_source):
        return SignalResult(state="unavailable", status="blocked_simulated_data",
                            signal_version=config.SIGNAL_VERSION)
    if len(navs) < 20:
        return SignalResult(state="unavailable", status="insufficient_data",
                            signal_version=config.SIGNAL_VERSION)
    ts = trend.score(navs)
    ms = momentum.score(navs)
    ss = sentiment.score(sentiment_values)
    rs = volatility.risk_score(navs)
    overall = round(0.45 * ts + 0.35 * ms + 0.20 * ss, 2)
    state = "positive" if overall >= 60 else ("negative" if overall <= 40 else "neutral")
    agreement = 1 - min(1.0, (max(ts, ms, ss) - min(ts, ms, ss)) / 100)
    confidence = round(min(0.95, max(0.35, 0.45 + 0.35 * agreement + 0.15 * abs(overall - 50) / 50)), 2)
    return SignalResult(trend_score=ts, momentum_score=ms, sentiment_score=ss,
                        risk_score=rs, overall_score=overall, confidence=confidence,
                        state=state, status="ok", signal_version=config.SIGNAL_VERSION)
