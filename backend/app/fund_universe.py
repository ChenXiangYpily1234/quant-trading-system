"""
基金全库模块
从东方财富拉取全量基金代码库（约 2.7 万只，含代码/简称/全名/类型/拼音），
本地缓存为 JSON，供前端「搜索并添加基金」使用（支持代码、中文名、拼音首字母）。
拉取失败时回退到内置精选清单，保证搜索功能始终可用。
"""
import json
import time
from typing import List, Dict, Optional

import httpx

from . import config, store

UNIVERSE_URL = "https://fund.eastmoney.com/js/fundcode_search.js"
CACHE_FILE = "fund_universe.json"
CACHE_TTL = 7 * 86400  # 7 天

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 拉取失败时的兜底清单（科技/AI/CPO 相关精选）
_FALLBACK: List[Dict] = [
    {"code": "005844", "name": "东方人工智能主题混合A", "type": "混合型-偏股", "pinyin": "DFRGZNZTHHA"},
    {"code": "006265", "name": "红土创新新科技股票A", "type": "股票型", "pinyin": "HTCXXKJGPA"},
    {"code": "008086", "name": "华夏中证5G通信主题ETF联接A", "type": "指数型", "pinyin": "HXZZ5GTXZTETFLJA"},
    {"code": "320007", "name": "诺安成长混合", "type": "混合型-偏股", "pinyin": "NACZHH"},
    {"code": "519674", "name": "银河创新成长混合A", "type": "混合型-偏股", "pinyin": "YHCXCZHHA"},
    {"code": "001513", "name": "易方达信息产业混合", "type": "混合型-偏股", "pinyin": "YFDXXCYHH"},
    {"code": "001856", "name": "前海开源国家比较优势混合A", "type": "混合型-偏股", "pinyin": "QHKYGJBJYSHHA"},
    {"code": "011609", "name": "国泰中证动漫游戏ETF联接A", "type": "指数型", "pinyin": "GTZZDMYXETFLJA"},
]

_mem: Optional[List[Dict]] = None
_mem_at: float = 0.0


def _parse(text: str) -> List[Dict]:
    s = text.find("[")
    e = text.rfind("]")
    if s == -1 or e == -1:
        return []
    arr = json.loads(text[s:e + 1])
    out: List[Dict] = []
    for row in arr:
        if not isinstance(row, list) or len(row) < 4:
            continue
        out.append({
            "code": row[0],
            "abbr": row[1],
            "name": row[2],
            "type": row[3],
            "pinyin": row[4] if len(row) > 4 else "",
        })
    return out


def _download() -> List[Dict]:
    try:
        with httpx.Client(timeout=25, headers={
            "User-Agent": UA, "Referer": "https://fund.eastmoney.com/",
        }, follow_redirects=True) as c:
            r = c.get(UNIVERSE_URL)
        if r.status_code != 200:
            return []
        r.encoding = r.encoding or "utf-8"
        return _parse(r.text)
    except Exception:
        return []


def load_universe(force: bool = False) -> List[Dict]:
    """加载基金全库：内存 -> 本地缓存 -> 远端下载 -> 兜底清单。"""
    global _mem, _mem_at
    now = time.time()
    if _mem and not force and (now - _mem_at) < 3600:
        return _mem

    cached = store.load(CACHE_FILE, None)
    if cached and not force:
        ts = cached.get("updated_at", 0)
        items = cached.get("items", [])
        if items and (now - ts) < CACHE_TTL:
            _mem, _mem_at = items, now
            return items

    items = _download()
    if items:
        store.save(CACHE_FILE, {"updated_at": now, "items": items})
        _mem, _mem_at = items, now
        return items

    if cached and cached.get("items"):
        _mem, _mem_at = cached["items"], now
        return _mem

    _mem, _mem_at = _FALLBACK, now
    return _FALLBACK


def universe_size() -> int:
    return len(load_universe())


def search(q: str, limit: int = 20) -> List[Dict]:
    """按代码 / 中文名 / 拼音缩写 搜索基金。代码前缀命中优先。"""
    q = (q or "").strip()
    if not q:
        return []
    ql = q.lower()
    qu = q.upper()
    items = load_universe()

    exact, code_pre, name_hit, py_hit = [], [], [], []
    for it in items:
        code = it["code"]
        name = it["name"]
        if code == q:
            exact.append(it)
        elif code.startswith(q):
            code_pre.append(it)
        elif ql in name.lower():
            name_hit.append(it)
        elif qu and (qu in (it.get("abbr") or "") or qu in (it.get("pinyin") or "")):
            py_hit.append(it)
        if len(exact) + len(code_pre) + len(name_hit) + len(py_hit) > limit * 6:
            break

    merged = exact + code_pre + name_hit + py_hit
    out = []
    for it in merged[:limit]:
        out.append({"code": it["code"], "name": it["name"], "type": it.get("type", "")})
    return out


def get_info(code: str) -> Optional[Dict]:
    for it in load_universe():
        if it["code"] == code:
            return {"code": it["code"], "name": it["name"], "type": it.get("type", "")}
    return None


def guess_category(name: str, ftype: str = "") -> str:
    """按基金名称推断主题分类，用于卡片分组展示。"""
    rules = [
        (("人工智能", "AI", "智能"), "人工智能"),
        (("光", "通信", "5G", "CPO"), "CPO/通信"),
        (("半导体", "芯片", "集成电路"), "半导体"),
        (("科技", "新科技"), "新科技"),
        (("信息", "TMT", "软件", "计算机", "云"), "TMT/算力"),
        (("新能源", "光伏", "电池"), "新能源"),
        (("医药", "医疗", "生物"), "医药"),
        (("消费", "白酒", "食品"), "消费"),
        (("军工", "国防"), "军工"),
        (("游戏", "动漫", "传媒"), "AI应用/传媒"),
        (("债", "货币"), "固收"),
    ]
    for kws, cat in rules:
        for kw in kws:
            if kw in name:
                return cat
    return ftype or "其他"
