"""Deprecated compatibility adapter for the explanation-only AI layer."""
import time
from typing import Any, Dict, List

from .ai import explain
from .schemas import AnalysisResult, NewsItem


def analyze(code: str, name: str, prediction: Dict[str, Any], news: List[NewsItem],
            allow_llm: bool = False) -> AnalysisResult:
    """Return the legacy response shape without delegating decisions to an LLM."""
    signal = prediction.get("signal") or {}
    risk = prediction.get("risk") or {}
    result = explain(name, signal, risk, [n.title for n in news if n.relevance > 0],
                     allow_llm=allow_llm)
    state = signal.get("state", "unavailable")
    trend = {"positive": "趋势增强", "neutral": "趋势中性",
             "negative": "趋势减弱"}.get(state, "实时分析暂不可用")
    key_news = [n.title for n in news if n.relevance > 0][:5]
    return AnalysisResult(
        code=code, name=name, generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        engine=result.engine, trend_prediction=trend, predicted_nav=None,
        predicted_change_pct=None, confidence=signal.get("confidence"),
        advice="查看分析", position_action="不提供仓位建议",
        risk_level={"low": "低", "medium": "中", "high": "高"}.get(
            risk.get("risk_level"), "暂无"),
        reasoning=result.summary + " " + result.risk_note,
        key_news=key_news,
    )
