"""
新闻抓取模块
- 抓取 config.NEWS_SOURCES + 用户在界面上自行添加的源（持久化 data/news_sources.json）
- 全部失败或无配置时，回退到内置「示例资讯库」（CPO/科技主题，明确标注）
- 对每条新闻做：相关度打分、情感打分、主题标签提取（供前端筛选）
- 支持按关键词 / 情感 / 标签过滤
"""
import time
import re
import html
import urllib.parse
import httpx
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

from . import config, store
from .schemas import NewsItem, NewsList

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SOURCES_FILE = "news_sources.json"
SOURCE_TIMEOUT = 6

POSITIVE = ["涨", "利好", "增长", "突破", "超预期", "上调", "看好", "受益",
            "订单", "扩产", "创新高", "大增", "回暖", "签约", "中标", "放量"]
NEGATIVE = ["跌", "利空", "下滑", "亏损", "下调", "风险", "制裁", "减持",
            "跌破", "暴雷", "收紧", "承压", "回调", "终止", "诉讼", "库存"]


# ---------------- 用户自定义新闻源（可在界面增删） ----------------
def list_sources() -> List[Dict]:
    return store.load(SOURCES_FILE, [])


def add_source(name: str, url: str, stype: str = "rss") -> Dict:
    if not url:
        raise ValueError("新闻源地址不能为空")
    data = list_sources()
    if any(s["url"] == url for s in data):
        raise ValueError("该新闻源已存在")
    item = {"name": name or url[:30], "url": url, "type": stype}
    data.append(item)
    store.save(SOURCES_FILE, data)
    return item


def remove_source(url: str) -> bool:
    data = list_sources()
    left = [s for s in data if s["url"] != url]
    if len(left) == len(data):
        return False
    store.save(SOURCES_FILE, left)
    return True


def _all_sources() -> List[Dict]:
    return list(config.NEWS_SOURCES) + list_sources()


# ---------------- 打分与标签 ----------------
def _relevance(text: str, keywords: List[str] = None) -> float:
    kws = keywords or config.NEWS_KEYWORDS
    t = text.lower()
    score = 0.0
    for kw in kws:
        if kw.lower() in t:
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


def _tags(text: str, keywords: List[str] = None) -> List[str]:
    """按 keywords 命中提取主题标签（保留原始大小写用于展示，匹配时忽略大小写）。"""
    kws = keywords or config.NEWS_KEYWORDS
    t = text.lower()
    out = []
    for kw in kws:
        if kw.lower() in t:
            out.append(kw)
    return out[:5]


def _search_link(title: str, tags: List[str]) -> str:
    """内置示例资讯提供可点击的延伸检索链接（东方财富资讯搜索）。"""
    kw = tags[0] if tags else title[:8]
    return "https://so.eastmoney.com/news/s?keyword=" + urllib.parse.quote(kw)


# ---------------- 内置示例资讯（降级用，明确标注） ----------------
def _sample_news() -> List[NewsItem]:
    now = time.time()
    H = 3600
    samples = [
        ("算力需求爆发，CPO光模块龙头订单饱满排产至明年", "多家云厂商上调资本开支，1.6T光模块渗透率加速，产业链景气度持续上行。"),
        ("英伟达新一代AI芯片量产，带动光模块配套需求", "新一代GPU对高速互联要求提升，CPO（共封装光学）成为主流技术路线。"),
        ("半导体板块异动，设备材料国产化提速", "wafer厂扩产叠加国产替代，半导体设备订单同比高增。"),
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
        txt = title + summary
        tags = _tags(txt)
        items.append(NewsItem(
            title=title,
            link=_search_link(title, tags),
            source="示例数据(内置)",
            published=time.strftime("%Y-%m-%d %H:%M", time.localtime(now - i * 2 * H)),
            summary=summary,
            relevance=_relevance(txt),
            sentiment=_sentiment(txt),
            tags=tags,
        ))
    return sorted(items, key=lambda x: x.relevance, reverse=True)


# ---------------- 真实源抓取 ----------------
def _mk(title, link, source, published, summary, keywords: List[str] = None) -> NewsItem:
    txt = title + " " + (summary or "")
    return NewsItem(
        title=html.unescape(title),
        link=link or "#",
        source=source,
        published=published,
        summary=html.unescape(summary or "")[:200],
        relevance=_relevance(txt, keywords),
        sentiment=_sentiment(txt),
        tags=_tags(txt, keywords),
    )


def _tag_text(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S | re.I)
    if not m:
        return ""
    # 去掉 CDATA 包裹
    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S).strip()


def _extract_regex(content: bytes, name: str, keywords: List[str] = None) -> List[NewsItem]:
    """XML 不规范（含未转义字符等）时的兜底解析：用正则抽取 item/entry。"""
    text = content.decode("utf-8", "ignore")
    items: List[NewsItem] = []
    blocks = re.findall(r"<item[\s>].*?</item>|<entry[\s>].*?</entry>", text, re.S | re.I)
    for b in blocks:
        title = _tag_text(b, "title")
        link = _tag_text(b, "link")
        if not link:
            m = re.search(r"<link[^>]*href=\"([^\"]+)\"", b, re.I)
            link = m.group(1) if m else ""
        desc = _tag_text(b, "description") or _tag_text(b, "summary") or _tag_text(b, "content")
        pub = _tag_text(b, "pubDate") or _tag_text(b, "published") or _tag_text(b, "updated")
        if title:
            items.append(_mk(title, link, name, pub, desc, keywords))
    return items


def _fetch_rss(url: str, name: str, keywords: List[str] = None) -> List[NewsItem]:
    items: List[NewsItem] = []
    with httpx.Client(timeout=SOURCE_TIMEOUT, headers={"User-Agent": UA},
                      follow_redirects=True) as c:
        r = c.get(url)
    if r.status_code != 200:
        return items
    try:
        root = ET.fromstring(r.content)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub = item.findtext("pubDate")
            if title:
                items.append(_mk(title, link, name, pub, desc, keywords))
        if not items:
            ns = "{http://www.w3.org/2005/Atom}"
            for entry in root.iter(ns + "entry"):
                title = (entry.findtext(ns + "title") or "").strip()
                link_el = entry.find(ns + "link")
                link = link_el.get("href") if link_el is not None else ""
                summary = (entry.findtext(ns + "summary") or "").strip()
                pub = entry.findtext(ns + "updated")
                if title:
                    items.append(_mk(title, link, name, pub, summary, keywords))
    except ET.ParseError:
        items = _extract_regex(r.content, name, keywords)
    return items


def _fetch_api(url: str, name: str, json_map: Dict[str, str],
               keywords: List[str] = None) -> List[NewsItem]:
    items: List[NewsItem] = []
    with httpx.Client(timeout=SOURCE_TIMEOUT, headers={"User-Agent": UA},
                      follow_redirects=True) as c:
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
            items.append(_mk(title, link, name, pub, desc, keywords))
    return items


def get_news(limit: int = 30) -> NewsList:
    items: List[NewsItem] = []
    ok_sources, failed_sources = [], []
    for src in _all_sources()[:6]:
        try:
            if src.get("type") == "api":
                got = _fetch_api(src["url"], src.get("name", "API"),
                                 src.get("json_map", {}), src.get("keywords"))
            else:
                got = _fetch_rss(src["url"], src.get("name", "RSS"), src.get("keywords"))
            if got:
                items.extend(got)
                ok_sources.append(src.get("name", src["url"]))
            else:
                failed_sources.append(src.get("name", src["url"]))
        except Exception:
            failed_sources.append(src.get("name", src["url"]))

    if items:
        source_note = "实时抓取：" + "、".join(ok_sources)
        if failed_sources:
            source_note += f"（{len(failed_sources)} 个源失败）"
    else:
        items = _sample_news()
        source_note = "内置示例资讯（尚未接入可用新闻源，可在「新闻中心」右上角添加 RSS 源）"

    seen = set()
    unique: List[NewsItem] = []
    for it in items:
        if it.title in seen:
            continue
        seen.add(it.title)
        unique.append(it)
    unique.sort(key=lambda x: (x.relevance, x.sentiment), reverse=True)

    all_tags = sorted({t for it in unique for t in it.tags})
    return NewsList(items=unique[:limit], total=len(unique),
                    source_note=source_note, tags=all_tags)


def filter_news(nl: NewsList, q: Optional[str] = None, sentiment: Optional[str] = None,
                tag: Optional[str] = None, sort: str = "relevance",
                limit: int = 30) -> NewsList:
    """按关键词 / 情感 / 标签过滤与排序（前端交互驱动）。"""
    items = list(nl.items)
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i.title.lower() or ql in (i.summary or "").lower()]
    if tag:
        items = [i for i in items if tag in i.tags]
    if sentiment == "pos":
        items = [i for i in items if i.sentiment > 0.1]
    elif sentiment == "neg":
        items = [i for i in items if i.sentiment < -0.1]
    elif sentiment == "neu":
        items = [i for i in items if -0.1 <= i.sentiment <= 0.1]

    if sort == "sentiment":
        items.sort(key=lambda x: x.sentiment, reverse=True)
    elif sort == "risk":
        items.sort(key=lambda x: x.sentiment)
    elif sort == "time":
        items.sort(key=lambda x: (x.published or ""), reverse=True)
    else:
        items.sort(key=lambda x: (x.relevance, x.sentiment), reverse=True)

    return NewsList(items=items[:limit], total=len(items),
                    source_note=nl.source_note, tags=nl.tags)
