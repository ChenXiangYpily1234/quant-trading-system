"""Pydantic 响应模型"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class NavPoint(BaseModel):
    date: str
    nav: float            # 单位净值
    acc_nav: Optional[float] = None   # 累计净值
    change_pct: Optional[float] = None  # 当日涨跌%


class FundSummary(BaseModel):
    code: str
    name: str
    category: str
    note: Optional[str] = None
    focus: bool = False              # 是否为重点关注基金
    latest_nav: Optional[float] = None
    latest_date: Optional[str] = None
    day_change_pct: Optional[float] = None     # 最新一日涨跌
    estimate_nav: Optional[float] = None       # 盘中模拟估值
    estimate_change_pct: Optional[float] = None
    direction: Optional[str] = None            # 预测方向 up/down/flat
    confidence: Optional[float] = None         # 预测置信度 0-1
    advice: Optional[str] = None               # 操作建议
    data_source: str = "unknown"               # real / simulated


class FundDetail(BaseModel):
    code: str
    name: str
    category: str
    note: Optional[str] = None
    focus: bool = False              # 是否为重点关注基金
    data_source: str
    history: List[NavPoint]
    ma5: List[Optional[float]]
    ma20: List[Optional[float]]
    prediction: Dict[str, Any]
    recommendation: Dict[str, Any]
    sentiment: Dict[str, Any]


class NewsItem(BaseModel):
    title: str
    link: str
    source: str
    published: Optional[str] = None
    summary: str = ""
    relevance: float = 0.0     # 相关度打分
    sentiment: float = 0.0      # 情感得分 -1~1


class NewsList(BaseModel):
    items: List[NewsItem]
    total: int
    source_note: str


class AnalysisResult(BaseModel):
    code: str
    name: str
    generated_at: str
    engine: str                # "llm" / "rule-based"
    trend_prediction: str
    predicted_nav: Optional[float] = None
    predicted_change_pct: Optional[float] = None
    confidence: Optional[float] = None
    advice: str                # 买入/卖出/加仓/减仓/持有/观望
    position_action: str       # 加仓/减仓/持有/清仓/建仓
    risk_level: str            # 低/中/高
    reasoning: str
    key_news: List[str] = []
