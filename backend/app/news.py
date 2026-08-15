"""
新闻抓取模块
- 优先抓取 config.NEWS_SOURCES 配置的 RSS / JSON 源
- 全部失败或无配置时，回退到内置「示例资讯库」（CPO/科技主题，明确标注）
- 对每条新闻做：相关度打分（关键词命中）、情感打分（正负面词典）
"""
import time
import html
import httpx
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

from . import config
from .schemas import NewsItem, NewsList

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

POSITIVE = ["涨", "利好", "增长", "突破", "超预期", "上调", "看好", "受益",
            "订单", "扩产", "创新高", "大增", "回暖", "签约", "中标", "放量"]
NEGATIVE = ["跌", "利空", "下滑", "亏损", "下调", "风险", "制裁", "减持",
            "跌破", "暴雷", "收紧", "承压", "回调", "终止", "诉讼", "库存"]


# ---------------- 内置示例资讯（降级用，明确标注） ----------------
def _sample_news() -> List[NewsItem]:
    now = time.time()
    H = 3600
    samples = [
        ("算力需求爆发，CPO光模块龙头订单饱满排产至明年", "多家云厂商上调资本开支，1.6T光模块渗透率加速，产业链景气度持续上行。"),
        ("英伟达新一代AI芯片量产，带动光模块配套需求", "新一代GPU对高速互联要求提升，CPO（共封装光学）成为主流技术路线。"),
        ("半导体板块异动，设备材料国产化提速", " wafer厂扩产叠加国产替代，半导体设备订单同比高增。"),
        ("工信部：加快算力网络与数据中心绿色化建设", "政策加码智算中心，液冷、服务器、光模块迎来增量市场。"),
        ("某5G通信ETF获资金净流入，机构看好通信估值修复", "通信板块估值处于历史低位，光模块业绩兑现驱动修复行情。"),
        ("AI应用端活跃，机器人板块受关注", "人形机器人量产预期升温，相关TMT基金净值弹性增强。"),
        ("风险提示：海外制裁升级或扰动半导体供应链", "部分标的出口受限，短期波动加大，建议控制仓位。"),
        ("基金二季报披露：多只科技基金加仓算力产业链", "主动权益基金集中配置CPO、半导体，抱团趋势延续。"),
        ("数据中心液冷渗透率提升，相关概念股走强", "高功耗AI服务器推动液冷方案普及，产业链公司订单可见度提升。"),
        ("机构观点：科技成长仍是中期主线，但需警惕估值分化", "建议均衡配置，逢回调分批布局具备业绩支撑的标的。"),
        ("北向资金今日净买入科技板块超20亿元", "外资回流成长股，半导体、通信设备获重点加仓。"),
        ("某芯片公司发布超预期业绩，毛利率创历史新高", "AI相关收入占比提升，盈利能力显著改善。"),
    ]
    items = []
    for i, (title, summary) in enumerate(samples):
        items.append(NewsItem(
            title=title,
            link="#",
            source="示例数据(内置)",
            published=time.strftime("%Y-%m-%d %H:%M", time.localtime(now - i * 2 * H)),
            summary=summary,
            relevance=_relevance(title + summary),
            sentiment=_sentiment(title + summary),
        ))
    return sorted(items, key=lambda x: x.relevance, reverse=True)


# ---------------- 打分 ----------------
def _relevance(text: str) -> float:
    t = text.lower()
    score = 0.0
    for kw in config.NEWS_KEYWORDS:
        if kw.lower() in t:
            # CPO/光模块/算力等核心词权重更高
            weight = 2.0 if kw.lower() in ("cpo", "光模块", "算力") else 1.0
            score += weight
    return min(score, 10.0)


def _sentiment(text: str) -> float:
    pos = sum(text.count(w) for w in POSITIVE)
    neg = sum(text.count(w) for w in NEGATIVE)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)


# ---------------- 真实源抓取 ----------------
def _fetch_rss(url: str, name: str) -> List[NewsItem]:
    items: List[NewsItem] = []
    with httpx.Client(timeout=config.REQUEST_TIMEOUT, headers={"User-Agent": UA}) as c:
        r = c.get(url)
    if r.status_code != 200:
        return items
    root = ET.fromstring(r.content)
    # RSS
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = item.findtext("pubDate") or item.findtext("dc:date", namespaces={"dc": "http://purl.org/dc/elements/1.1/"})
        if title:
            items.append(_mk(title, link, name, pub, desc))
    # Atom
    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.get("href") if link_el is not None else ""
            summary = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
            pub = entry.findtext("{http://www.w3.org/2005/Atom}updated")
            if title:
                items.append(_mk(title, link, name, pub, summary))
    return items


def _fetch_api(url: str, name: str, json_map: Dict[str, str]) -> List[NewsItem]:
    items: List[NewsItem] = []
    with httpx.Client(timeout=config.REQUEST_TIMEOUT, headers={"User-Agent": UA}) as c:
        r = c.get(url)
    if r.status_code != 200:
        return items
    data = r.json()
    arr = data
    for key in json_map.get("list_path", "").split("."):
        if not key:
            continue
        arr = arr.get(key, []) if isinstance(arr, dict) else arr
    for row in (arr or []):
        if not isinstance(row, dict):
            continue
        title = str(row.get(json_map.get("title", "title"), "") or "")
        link = str(row.get(json_map.get("link", "link"), "") or "")
        desc = str(row.get(json_map.get("summary", "summary"), "") or "")
        pub = row.get(json_map.get("published", "published"))
        if title:
            items.append(_mk(title, link, name, pub, desc))
    return items


def _mk(title, link, source, published, summary) -> NewsItem:
    txt = title + " " + summary
    return NewsItem(
        title=html.unescape(title),
        link=link,
        source=source,
        published=published,
        summary=html.unescape(summary)[:200],
        relevance=_relevance(txt),
        sentiment=_sentiment(txt),
    )


def get_news(limit: int = 20) -> NewsList:
    items: List[NewsItem] = []
    source_note = "实时抓取"
    try:
        for src in config.NEWS_SOURCES:
            try:
                if src.get("type") == "rss":
                    items.extend(_fetch_rss(src["url"], src.get("name", "RSS")))
                elif src.get("type") == "api":
                    items.extend(_fetch_api(src["url"], src.get("name", "API"), src.get("json_map", {})))
            except Exception:
                continue
    except Exception:
        items = []

    if not items:
        items = _sample_news()
        source_note = "内置示例数据（未配置/无法访问外部新闻源，可在 config.NEWS_SOURCES 中接入真实源）"

    # 去重 + 按相关度排序
    seen = set()
    unique = []
    for it in items:
        key = it.title
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    unique.sort(key=lambda x: (x.relevance, x.sentiment), reverse=True)
    return NewsList(items=unique[:limit], total=len(unique), source_note=source_note)
