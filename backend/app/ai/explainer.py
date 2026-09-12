import json
import re
import httpx
from typing import Any, Dict, List, Optional
from pydantic import ValidationError
from .. import config
from .prompts import SYSTEM, explanation_prompt
from .schemas import Explanation


def _fallback(name: str, signal: Dict[str, Any], risk: Dict[str, Any]) -> Explanation:
    if signal.get("status") != "ok":
        return Explanation(headline="实时分析暂不可用", summary="当前数据不能用于生成研究信号。",
                           key_points=["请等待真实行情恢复后再查看趋势分析"],
                           risk_note="模拟或不足的数据不会进入信号、回测和组合调整。")
    state = {"positive": "增强", "neutral": "中性", "negative": "减弱"}.get(signal.get("state"), "暂无")
    level = {"low": "低", "medium": "中", "high": "高"}.get(risk.get("risk_level"), "暂无")
    return Explanation(headline=f"{name}趋势{state}",
                       summary=f"趋势评分 {signal.get('trend_score')}/100，综合评分 {signal.get('overall_score')}/100。",
                       key_points=[f"动量评分 {signal.get('momentum_score')}/100", f"置信度 {round(signal.get('confidence', 0)*100)}%"],
                       risk_note=f"当前风险等级：{level}。该结果是数据解释，不构成交易建议。")


def _call(name: str, signal: Dict[str, Any], risk: Dict[str, Any], news_titles: List[str]) -> Optional[Explanation]:
    cfg = config.LLM_CONFIG
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    payload = {"model": cfg["model"], "messages": [{"role": "system", "content": SYSTEM},
               {"role": "user", "content": explanation_prompt(name, signal, risk, news_titles)}], "temperature": 0.1}
    try:
        with httpx.Client(timeout=cfg.get("timeout", 12)) as client:
            response = client.post(f"{cfg['base_url'].rstrip('/')}/chat/completions", json=payload,
                                   headers={"Authorization": f"Bearer {cfg['api_key']}"})
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
        return Explanation(**parsed, engine="llm")
    except (httpx.HTTPError, KeyError, ValueError, ValidationError):
        return None


def explain(name: str, signal: Dict[str, Any], risk: Dict[str, Any], news_titles: List[str],
            allow_llm: bool = False) -> Explanation:
    # 允许一次格式/网络重试；第二次失败后确定性降级。
    if allow_llm:
        return _call(name, signal, risk, news_titles) or _call(name, signal, risk, news_titles) or _fallback(name, signal, risk)
    return _fallback(name, signal, risk)
