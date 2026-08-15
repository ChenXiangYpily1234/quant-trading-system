"""
自选基金管理（持久化）
支持：新增 / 删除 / 切换重点关注 / 修改分类备注 / 恢复默认。
首次运行时用 config.DEFAULT_FUNDS 初始化；之后以 data/watchlist.json 为准。
"""
from typing import List, Dict, Optional

from . import config, store, fund_universe

FILE = "watchlist.json"


def _default() -> List[Dict]:
    return [dict(f) for f in config.DEFAULT_FUNDS]


def list_all() -> List[Dict]:
    data = store.load(FILE, None)
    if not data or not isinstance(data, list) or not data:
        data = _default()
        store.save(FILE, data)
    # 兼容旧数据：补齐字段
    for f in data:
        f.setdefault("focus", False)
        f.setdefault("category", "其他")
        f.setdefault("note", "")
    return data


def get(code: str) -> Optional[Dict]:
    return next((f for f in list_all() if f["code"] == code), None)


def codes() -> List[str]:
    return [f["code"] for f in list_all()]


def add(code: str, category: str = None, note: str = None,
        focus: bool = False, name: str = None) -> Dict:
    """添加自选。自动从基金全库补全名称与分类。已存在则返回既有项。"""
    code = (code or "").strip()
    if not code:
        raise ValueError("基金代码不能为空")
    data = list_all()
    existing = next((f for f in data if f["code"] == code), None)
    if existing:
        return existing

    info = fund_universe.get_info(code)
    if not info and not name:
        raise ValueError(f"未找到基金代码 {code}，请确认后重试")
    fname = name or info["name"]
    ftype = (info or {}).get("type", "")
    item = {
        "code": code,
        "name": fname,
        "category": category or fund_universe.guess_category(fname, ftype),
        "note": note or (f"{ftype} · 用户添加" if ftype else "用户添加"),
        "focus": bool(focus),
    }
    data.append(item)
    store.save(FILE, data)
    return item


def remove(code: str) -> bool:
    data = list_all()
    left = [f for f in data if f["code"] != code]
    if len(left) == len(data):
        return False
    store.save(FILE, left)
    return True


def toggle_focus(code: str) -> Optional[bool]:
    data = list_all()
    for f in data:
        if f["code"] == code:
            f["focus"] = not f.get("focus", False)
            store.save(FILE, data)
            return f["focus"]
    return None


def update(code: str, category: str = None, note: str = None) -> Optional[Dict]:
    data = list_all()
    for f in data:
        if f["code"] == code:
            if category is not None:
                f["category"] = category
            if note is not None:
                f["note"] = note
            store.save(FILE, data)
            return f
    return None


def reset() -> List[Dict]:
    data = _default()
    store.save(FILE, data)
    return data
