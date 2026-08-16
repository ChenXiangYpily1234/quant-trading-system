"""
量化交易系统 - 全局配置
集中管理基金列表、新闻源、大模型与刷新策略。
所有可调项均可通过环境变量覆盖，便于部署。
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict

# ---------- 监控基金列表（CPO / 科技主题） ----------
# code: 天天基金/东方财富基金代码
# category: 主题分类，用于聚合与筛选
# 这些为真实存在的基金代码，系统会尝试抓取其实时净值；
# 若抓取失败，则自动降级为确定性模拟数据并标注。
# focus=True 的基金为「重点关注」基金，会在仪表盘置顶并标记「重点」徽章。
# 当前重点：东方人工智能主题混合A(005844) 与 红土创新新科技股票(006265)，
# 二者均重仓 AI/CPO 产业链（中际旭创、新易盛、天孚通信等）。
DEFAULT_FUNDS: List[Dict] = [
    {"code": "005844", "name": "东方人工智能主题混合A", "category": "人工智能", "note": "AI主题核心标的（重点关注）", "focus": True},
    {"code": "006265", "name": "红土创新新科技股票", "category": "新科技/CPO", "note": "重仓中际旭创/新易盛/天孚通信（重点关注）", "focus": True},
    {"code": "008086", "name": "华夏中证5G通信主题ETF联接A", "category": "CPO/通信", "note": "光模块/通信设备核心标的"},
    {"code": "320007", "name": "诺安成长混合", "category": "半导体", "note": "重仓半导体，高弹性"},
    {"code": "519674", "name": "银河创新成长混合A", "category": "半导体", "note": "科技成长风格"},
    {"code": "001513", "name": "易方达信息产业混合", "category": "TMT", "note": "覆盖算力/AI产业链"},
    {"code": "001856", "name": "前海开源国家比较优势混合A", "category": "科技成长", "note": "成长均衡"},
    {"code": "011609", "name": "国泰中证动漫游戏ETF联接A", "category": "AI应用", "note": "AI应用端"},
]

# ---------- 新闻抓取配置 ----------
# 支持两类源：
#   type="rss"    : 标准 RSS/Atom，按 item/title/link/pubDate/description 解析
#   type="api"    : 返回 JSON 列表，需指定字段映射 json_map
# 直连财经新闻接口常被反爬拦截，故默认源可能失败；
# 失败时系统回退到内置的「示例资讯库」（已按 CPO/科技主题整理）。
NEWS_SOURCES: List[Dict] = [
    # 用户可在此追加自己的新闻源，例如：
    # {"type": "rss", "name": "我的RSS", "url": "https://example.com/feed.xml", "keywords": ["CPO", "光模块", "算力"]},
]

# 关键词（用于新闻相关度打分与过滤）
NEWS_KEYWORDS: List[str] = [
    "CPO", "光模块", "算力", "人工智能", "AI", "半导体", "芯片", "5G",
    "通信", "数字经济", "数据中心", "英伟达", "液冷", "服务器", "机器人",
]

# ---------- 大模型（辅助决策）配置 ----------
# 支持任意 OpenAI 兼容接口。配置 OPENAI_API_KEY 后启用真实大模型；
# 未配置时自动回退到内置「规则引擎分析师」，保证系统始终可用。
LLM_CONFIG = {
    "enabled": bool(os.getenv("OPENAI_API_KEY")),
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "temperature": 0.3,
    "timeout": 12,
}

# ---------- 刷新与缓存策略 ----------
REFRESH_INTERVAL_SECONDS = int(os.getenv("REFRESH_INTERVAL", "15"))  # 后台自动刷新间隔
REQUEST_TIMEOUT = 10           # 单次抓取超时（秒）
HISTORY_DAYS = 60              # 默认历史净值天数（约3页，足以计算MA20）
PREDICT_DAYS = 5               # 预测未来天数
CACHE_TTL_SECONDS = 60         # 净值/状态缓存有效期（秒）
FUND_CACHE_TTL = 600            # 历史净值缓存时长（秒，分钟级刷新即可，日内实时感由模拟估值提供）
LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN", "300"))  # LLM 接口不可达后的熔断冷却时长（秒）

# 是否允许在无法获取真实数据时生成模拟数据
ALLOW_SIMULATED_DATA = os.getenv("ALLOW_SIM", "true").lower() == "true"
