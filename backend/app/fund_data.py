"""
基金数据模块
- 优先抓取东方财富历史净值（真实日频数据）
- 抓取失败则降级为确定性模拟数据（按基金代码播种，形态贴近科技基金）
- 提供「盘中模拟估值」以呈现实时变化（真实盘中报价接口未开放，明确标注）
"""
import re
import time
import math
import hashlib
import httpx
from typing import List, Optional, Tuple

import numpy as np

from . import config
from .schemas import NavPoint

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
NAV_API = "https://api.fund.eastmoney.com/f10/lsjz"


def _seed_from_code(code: str) -> int:
    return int(hashlib.md5(code.encode()).hexdigest(), 16) % (2 ** 31)


def _parse_jsonp(text: str):
    """解析 JSONP：x({...}) -> dict"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    import json
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def fetch_nav_real(code: str, days: int = 60) -> Optional[List[NavPoint]]:
    """抓取东方财富历史净值（按页翻取，每页20条），返回按日期升序的 NavPoint 列表。失败返回 None。"""
    try:
        all_rows: List[dict] = []
        per = 20
        page = 1
        with httpx.Client(timeout=config.REQUEST_TIMEOUT, headers={
            "User-Agent": UA,
            "Referer": "https://fundf10.eastmoney.com/",
        }) as client:
            while len(all_rows) < days and page <= 20:
                url = (f"{NAV_API}?callback=x&fundCode={code}"
                       f"&pageIndex={page}&pageSize={per}")
                r = client.get(url)
                if r.status_code != 200:
                    break
                data = _parse_jsonp(r.text)
                rows = (data or {}).get("Data", {}).get("LSJZList") or []
                if not rows:
                    break
                all_rows.extend(rows)
                if len(rows) < per:
                    break
                page += 1
        if not all_rows:
            return None
        # 去重（按日期）
        seen = set()
        points: List[NavPoint] = []
        for row in all_rows:
            try:
                nav = float(row.get("DWJZ"))
            except (TypeError, ValueError):
                continue
            d = row.get("FSRQ")
            if d in seen:
                continue
            seen.add(d)
            acc = row.get("LJJZ")
            acc_f = float(acc) if acc not in (None, "") else None
            chg = row.get("JZZZL")
            chg_f = float(chg) if chg not in (None, "") else None
            points.append(NavPoint(date=d, nav=nav, acc_nav=acc_f, change_pct=chg_f))
        if len(points) < 5:
            return None
        points.reverse()  # 接口返回最新在前，翻转为时间升序
        return points[-days:] if days else points
    except Exception:
        return None


def simulate_nav(code: str, days: int = 120) -> List[NavPoint]:
    """确定性模拟：以基金代码为种子生成贴近科技基金的高波动净值序列。"""
    rng = np.random.default_rng(_seed_from_code(code))
    # 不同基金设定不同长期趋势与波动
    drift = rng.uniform(-0.0008, 0.0012)        # 日漂移
    vol = rng.uniform(0.012, 0.026)             # 日波动
    nav = rng.uniform(0.6, 1.4)
    # 构造交易日（粗略：跳过周末）
    end = time.time()
    day_sec = 86400
    dates = []
    cur = end - (days - 1) * day_sec
    while len(dates) < days:
        d = time.localtime(cur)
        if d.tm_wday < 5:  # 周一到周五
            dates.append(time.strftime("%Y-%m-%d", d))
        cur += day_sec
    dates = dates[-days:]

    points: List[NavPoint] = []
    prev_nav = nav
    for i, date in enumerate(dates):
        # 偶发趋势切换，制造科技基金常见的波段
        if i % 25 == 0:
            drift = rng.uniform(-0.0008, 0.0012)
            vol = rng.uniform(0.012, 0.026)
        shock = rng.normal(drift, vol)
        nav = max(0.3, nav * (1 + shock))
        chg = (nav / prev_nav - 1) * 100 if prev_nav else 0.0
        points.append(NavPoint(
            date=date,
            nav=round(nav, 4),
            acc_nav=round(nav * rng.uniform(1.0, 4.0), 4),
            change_pct=round(chg, 2),
        ))
        prev_nav = nav
    return points


def get_nav(code: str, days: int = 120) -> Tuple[List[NavPoint], str]:
    """获取净值：优先真实，失败降级模拟。返回 (points, source)。"""
    if config.ALLOW_SIMULATED_DATA:
        real = fetch_nav_real(code, days)
        if real and len(real) >= 5:
            return real, "real"
    # 降级
    return simulate_nav(code, days), "simulated"


def intraday_estimate(code: str, latest_nav: float, source: str) -> Tuple[float, float]:
    """
    盘中模拟估值：基于时间缓慢漂移，使仪表盘呈现「实时」变化。
    真实盘中报价接口未开放，此处为模拟，前端明确标注为「模拟估值」。
    """
    if latest_nav is None:
        return None, None
    now = time.time()
    minute = int(now // 60)
    seed = _seed_from_code(code + str(minute // 3))  # 每3分钟换一次种子，平滑变化
    rng = np.random.default_rng(seed)
    # 振幅与基金波动性正相关；以正弦叠加噪声模拟盘中波动
    wave = math.sin(now / 90.0 + _seed_from_code(code) % 100) * 0.6
    noise = (rng.random() - 0.5) * 0.8
    chg_pct = round(wave + noise, 2)
    est = round(latest_nav * (1 + chg_pct / 100), 4)
    return est, chg_pct
