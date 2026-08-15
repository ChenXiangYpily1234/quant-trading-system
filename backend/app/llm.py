"""
大模型辅助决策模块
- 配置 OPENAI_API_KEY 后调用任意 OpenAI 兼容大模型，结合净值指标+新闻给出研判
- 未配置时回退到内置「规则引擎分析师」（基于指标与新闻情感的确定性决策）
两种模式对外接口一致，返回 AnalysisResult。
"""
import json
import time
import re
import httpx
from typing import List, Dict, Any, Optional

from . import config
from .schemas import AnalysisResult, NavPoint, NewsItem


def _build_prompt(name: str, code: str, prediction: Dict[str, Any], news: List[NewsItem]) -> str:
    ind = prediction.get("indicators", {})
    top_news = "\n".join(
        f"- [{n.sentiment:+.1f}] {n.title}" for n in news[:8] if n.relevance > 0
    ) or "- (无相关新闻)"
    return f"""基金：{name}（{code}）
技术指标：近5日动量{ind.get('momentum5')}%，近20日{ind.get('momentum20')}%，RSI={ind.get('rsi')}，日波动{ind.get('volatility')}%，最新净值{ind.get('latest_nav')}
量化预测：方向={prediction.get('direction')}，预测5日后净值={prediction.get('predicted_nav')}（{prediction.get('predicted_change_pct')}%），置信度={prediction.get('confidence')}
相关新闻（情感分）：
{top_news}

请以JSON输出研判（不要包含多余文字）：
{{"trend_prediction":"短期走势描述","predicted_nav":数值或null,"predicted_change_pct":数值或null,"confidence":0到1,"advice":"买入/卖出/加仓/减仓/持有/观望","position_action":"建仓/加仓/减仓/清仓/持有","risk_level":"低/中/高","reasoning":"不超过120字的分析依据"}}"""


def _call_llm(name: str, code: str, prediction: Dict[str, Any], news: List[NewsItem]) -> Optional[Dict[str, Any]]:
    cfg = config.LLM_CONFIG
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    try:
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": "你是资深量化分析师，只输出JSON。"},
                {"role": "user", "content": _build_prompt(name, code, prediction, news)},
            ],
            "temperature": cfg["temperature"],
        }
        with httpx.Client(timeout=cfg["timeout"], headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }) as c:
            r = c.post(f"{cfg['base_url'].rstrip('/')}/chat/completions", json=payload)
        if r.status_code != 200:
            return None
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception:
        return None


def _rule_based(name: str, code: str, prediction: Dict[str, Any], news: List[NewsItem]) -> Dict[str, Any]:
    ind = prediction.get("indicators", {})
    direction = prediction.get("direction")
    conf = prediction.get("confidence", 0.5)
    rsi = ind.get("rsi", 50)
    vol = ind.get("volatility", 1.0)
    ns = 0.0
    top = [n for n in news if n.relevance > 0][:8]
    if top:
        ns = sum(n.sentiment for n in top) / len(top)

    # 决策矩阵
    if direction == "up":
        if conf >= 0.62 and rsi < 72:
            advice, action = "加仓", "加仓"
        elif rsi >= 75:
            advice, action = "持有（高位谨慎）", "持有"
        else:
            advice, action = "持有/小幅买入", "持有"
    elif direction == "down":
        if conf >= 0.62 and rsi > 28:
            advice, action = "减仓", "减仓"
        elif rsi < 30:
            advice, action = "观望（超跌）", "持有"
        else:
            advice, action = "减仓/观望", "减仓"
    else:
        advice, action = "持有（震荡）", "持有"

    risk = "高" if vol >= 2.0 else ("中" if vol >= 1.0 else "低")

    trend = ("短期（%d日）震荡上行" % prediction.get("horizon_days", 5)) if direction == "up" else (
        "短期（%d日）震荡下行" % prediction.get("horizon_days", 5) if direction == "down" else "短期（%d日）横盘震荡" % prediction.get("horizon_days", 5))

    reasoning = (f"{prediction.get('rationale','')} "
                 f"新闻面{'偏多' if ns>0.1 else ('偏空' if ns<-0.1 else '中性')}。"
                 f"RSI={rsi}（{'超买' if rsi>70 else '超卖' if rsi<30 else '中性'}），"
                 f"波动{vol:.2f}%属{risk}风险，建议{advice}。")

    return {
        "trend_prediction": trend,
        "predicted_nav": prediction.get("predicted_nav"),
        "predicted_change_pct": prediction.get("predicted_change_pct"),
        "confidence": conf,
        "advice": advice,
        "position_action": action,
        "risk_level": risk,
        "reasoning": reasoning,
    }


def analyze(code: str, name: str, prediction: Dict[str, Any], news: List[NewsItem]) -> AnalysisResult:
    llm_out = _call_llm(name, code, prediction, news)
    engine = "llm" if llm_out else "rule-based"
    if not llm_out:
        llm_out = _rule_based(name, code, prediction, news)

    key_news = [n.title for n in news if n.relevance > 0][:5]
    return AnalysisResult(
        code=code,
        name=name,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        engine=engine,
        trend_prediction=llm_out.get("trend_prediction", ""),
        predicted_nav=llm_out.get("predicted_nav"),
        predicted_change_pct=llm_out.get("predicted_change_pct"),
        confidence=llm_out.get("confidence"),
        advice=llm_out.get("advice", "持有"),
        position_action=llm_out.get("position_action", "持有"),
        risk_level=llm_out.get("risk_level", "中"),
        reasoning=llm_out.get("reasoning", ""),
        key_news=key_news,
    )
