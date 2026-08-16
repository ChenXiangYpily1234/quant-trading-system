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
    position_action: Optional[str] = None      # 仓位动作
    risk_level: Optional[str] = None           # 风险等级
    predicted_change_pct: Optional[float] = None
    return_20d: Optional[float] = None         # 近20日涨幅%
    risk: Optional[Dict[str, Any]] = None      # 风险指标（年化/波动/回撤/夏普/索提诺/卡玛）
    valuation: Optional[Dict[str, Any]] = None # 估值温度 {temp, label, nav_pct_rank, ma_ratio}
    sparkline: List[float] = []                # 迷你走势（近30点）
    data_source: str = "unknown"               # real / simulated
    held: bool = False                         # 是否已在持仓中


class FundDetail(BaseModel):
    code: str
    name: str
    category: str
    note: Optional[str] = None
    focus: bool = False              # 是否为重点关注基金
    data_source: str
    latest_date: Optional[str] = None
    days: int = 0
    history: List[NavPoint]
    ma5: List[Optional[float]]
    ma20: List[Optional[float]]
    indicators: Dict[str, Any] = {}   # ma10/ma60/boll/macd/kdj/rsi 序列
    stats: Dict[str, Any] = {}        # 区间业绩统计（含风险指标）
    valuation: Optional[Dict[str, Any]] = None  # 估值温度 {temp, label, nav_pct_rank, ma_ratio}
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
    tags: List[str] = []        # 命中的主题关键词


class NewsList(BaseModel):
    items: List[NewsItem]
    total: int
    source_note: str
    tags: List[str] = []        # 全部可用标签（供前端筛选）


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


# ---------- 请求体 ----------
class AddFundRequest(BaseModel):
    code: str
    category: Optional[str] = None
    note: Optional[str] = None
    focus: bool = False


class HoldingRequest(BaseModel):
    code: str
    shares: float
    cost_nav: float
    name: Optional[str] = ""
