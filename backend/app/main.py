"""FastAPI 主程序：基金监控、预测、新闻、决策、对比、回测、持仓的统一 API 层。"""
import asyncio
import io
import csv
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from . import (config, fund_data, news as news_mod, predictor, llm,
               indicators, backtest as bt, watchlist, portfolio, fund_universe)
from .cache import cache
from .schemas import (
    FundSummary, FundDetail, NewsList, AnalysisResult,
    AddFundRequest, HoldingRequest,
)

BASE = Path(__file__).resolve().parent.parent.parent  # .../quant-trading-system
FRONTEND = BASE / "frontend"

app = FastAPI(title="量化交易系统 · CPO/科技基金监控", version="2.0.0")

# 基金净值缓存：code -> {points, source, updated, days}
_fund_cache: Dict[str, Dict[str, Any]] = {}


# ---------------- 数据装配 ----------------
def _fetch_news_cached() -> NewsList:
    cached = cache.get("news")
    if cached:
        return cached
    nl = news_mod.get_news(limit=40)
    cache.set("news", nl, ttl=300)
    return nl


def ensure_fund(code: str, days: int = config.HISTORY_DAYS) -> Dict[str, Any]:
    """取净值序列。缓存中保存已抓取的最长序列，短区间直接切片，避免重复请求。"""
    entry = _fund_cache.get(code)
    now = time.time()
    if (entry and (now - entry["updated"]) < config.FUND_CACHE_TTL
            and entry.get("days", 0) >= days):
        return entry
    want = max(days, config.HISTORY_DAYS, entry.get("days", 0) if entry else 0)
    points, source = fund_data.get_nav(code, want)
    entry = {"points": points, "source": source, "updated": now, "days": want}
    _fund_cache[code] = entry
    return entry


def _slice(entry: Dict[str, Any], days: int):
    pts = entry["points"]
    return pts[-days:] if days and len(pts) > days else pts


def build_state(code: str, meta: Dict[str, str], news_list: NewsList,
                days: int = config.HISTORY_DAYS):
    entry = ensure_fund(code, days)
    points = _slice(entry, days)
    source = entry["source"]
    sentiment = predictor.aggregate_news_sentiment(news_list.items)
    pred = predictor.predict(code, points, sentiment)
    rec = llm.analyze(code, meta["name"], pred, news_list.items)
    est, est_chg = fund_data.intraday_estimate(code, pred["indicators"]["latest_nav"], source)
    latest = points[-1] if points else None
    return {
        "points": points, "source": source, "sentiment": sentiment,
        "pred": pred, "rec": rec, "estimate": est, "estimate_change": est_chg,
        "latest": latest,
    }


def _summary_of(f: Dict[str, Any], nl: NewsList, held_codes: set) -> FundSummary:
    st = build_state(f["code"], f, nl)
    lat = st["latest"]
    pts = st["points"]
    navs = [p.nav for p in pts]
    ret20 = round((navs[-1] / navs[-21] - 1) * 100, 2) if len(navs) >= 21 else (
        round((navs[-1] / navs[0] - 1) * 100, 2) if navs else None)
    return FundSummary(
        code=f["code"], name=f["name"], category=f.get("category", "其他"),
        note=f.get("note"), focus=f.get("focus", False),
        latest_nav=lat.nav if lat else None,
        latest_date=lat.date if lat else None,
        day_change_pct=lat.change_pct if lat else None,
        estimate_nav=st["estimate"], estimate_change_pct=st["estimate_change"],
        direction=st["pred"]["direction"], confidence=st["pred"]["confidence"],
        advice=st["rec"].advice, position_action=st["rec"].position_action,
        risk_level=st["rec"].risk_level,
        predicted_change_pct=st["pred"]["predicted_change_pct"],
        return_20d=ret20,
        sparkline=[round(v, 4) for v in navs[-30:]],
        data_source=st["source"],
        held=f["code"] in held_codes,
    )


# ---------------- 基础 ----------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "llm_enabled": config.LLM_CONFIG["enabled"],
        "llm_model": config.LLM_CONFIG["model"] if config.LLM_CONFIG["enabled"] else None,
        "funds_monitored": len(watchlist.list_all()),
        "holdings": len(portfolio.list_all()),
        "universe_size": fund_universe.universe_size(),
        "refresh_interval": config.REFRESH_INTERVAL_SECONDS,
        "predict_days": config.PREDICT_DAYS,
    }


# ---------------- 自选基金 ----------------
@app.get("/api/funds", response_model=List[FundSummary])
def list_funds():
    nl = _fetch_news_cached()
    held = {h["code"] for h in portfolio.list_all()}
    return [_summary_of(f, nl, held) for f in watchlist.list_all()]


@app.post("/api/funds")
def add_fund(req: AddFundRequest):
    try:
        item = watchlist.add(req.code.strip(), req.category, req.note, req.focus)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 立即预热数据，确认能取到净值
    entry = ensure_fund(item["code"])
    return {"status": "added", "fund": item, "data_source": entry["source"],
            "points": len(entry["points"])}


@app.delete("/api/funds/{code}")
def delete_fund(code: str):
    if not watchlist.remove(code):
        raise HTTPException(status_code=404, detail="该基金不在自选列表中")
    _fund_cache.pop(code, None)
    return {"status": "removed", "code": code}


@app.post("/api/funds/{code}/focus")
def toggle_focus(code: str):
    state = watchlist.toggle_focus(code)
    if state is None:
        raise HTTPException(status_code=404, detail="该基金不在自选列表中")
    return {"status": "ok", "code": code, "focus": state}


@app.post("/api/watchlist/reset")
def reset_watchlist():
    data = watchlist.reset()
    _fund_cache.clear()
    return {"status": "reset", "count": len(data)}


@app.get("/api/search")
def search_funds(q: str = Query("", description="基金代码/名称/拼音"),
                 limit: int = 15):
    results = fund_universe.search(q, limit=limit)
    owned = set(watchlist.codes())
    for r in results:
        r["added"] = r["code"] in owned
    return {"query": q, "count": len(results), "results": results,
            "universe_size": fund_universe.universe_size()}


# ---------------- 详情 / 指标 ----------------
@app.get("/api/funds/{code}", response_model=FundDetail)
def fund_detail(code: str, days: int = Query(60, ge=20, le=400)):
    meta = watchlist.get(code)
    if not meta:
        info = fund_universe.get_info(code)
        if not info:
            raise HTTPException(status_code=404, detail="基金代码未找到")
        meta = {"code": code, "name": info["name"], "category": info.get("type", ""),
                "note": "未加入自选", "focus": False}
    nl = _fetch_news_cached()
    st = build_state(code, meta, nl, days=days)
    pts = st["points"]
    navs = [p.nav for p in pts]
    ind_all = indicators.compute_all(navs)
    return FundDetail(
        code=code, name=meta["name"], category=meta.get("category", ""),
        note=meta.get("note"), focus=meta.get("focus", False),
        data_source=st["source"],
        latest_date=pts[-1].date if pts else None,
        days=len(pts),
        history=pts,
        ma5=ind_all["ma5"], ma20=ind_all["ma20"],
        indicators=ind_all,
        stats=indicators.perf_stats(navs),
        prediction=st["pred"],
        recommendation=st["rec"].dict(),
        sentiment=st["sentiment"],
    )


@app.get("/api/analysis/{code}", response_model=AnalysisResult)
def analysis(code: str, force: bool = False):
    meta = watchlist.get(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未配置")
    if force:
        _fund_cache.pop(code, None)
        cache.set("news", None, ttl=0)
    nl = _fetch_news_cached()
    st = build_state(code, meta, nl)
    return st["rec"]


@app.get("/api/export/{code}.csv")
def export_csv(code: str, days: int = Query(120, ge=20, le=400)):
    """导出净值 + 指标为 CSV（前端一键下载）。"""
    meta = watchlist.get(code) or fund_universe.get_info(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未找到")
    entry = ensure_fund(code, days)
    pts = _slice(entry, days)
    navs = [p.nav for p in pts]
    ind = indicators.compute_all(navs)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日期", "单位净值", "累计净值", "日涨跌%", "MA5", "MA20", "MA60",
                "BOLL上轨", "BOLL下轨", "MACD_DIF", "MACD_DEA", "RSI14"])
    for i, p in enumerate(pts):
        w.writerow([p.date, p.nav, p.acc_nav or "", p.change_pct if p.change_pct is not None else "",
                    ind["ma5"][i] or "", ind["ma20"][i] or "", ind["ma60"][i] or "",
                    ind["boll"]["upper"][i] or "", ind["boll"]["lower"][i] or "",
                    ind["macd"]["dif"][i] or "", ind["macd"]["dea"][i] or "",
                    ind["rsi"][i] or ""])
    data = "\ufeff" + buf.getvalue()  # BOM 便于 Excel 打开
    fname = f"{code}_nav_{time.strftime('%Y%m%d')}.csv"
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------------- 多基金对比 ----------------
@app.get("/api/compare")
def compare(codes: str = Query(..., description="逗号分隔的基金代码"),
            days: int = Query(60, ge=20, le=400)):
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:8]
    if not code_list:
        raise HTTPException(status_code=400, detail="请至少选择一只基金")

    series, stats, names, ret_map = [], [], {}, {}
    for code in code_list:
        meta = watchlist.get(code) or fund_universe.get_info(code) or {"name": code}
        entry = ensure_fund(code, days)
        pts = _slice(entry, days)
        if not pts:
            continue
        navs = [p.nav for p in pts]
        base = navs[0]
        names[code] = meta.get("name", code)
        series.append({
            "code": code, "name": names[code],
            "dates": [p.date for p in pts],
            "normalized": [round((v / base - 1) * 100, 2) for v in navs],
        })
        st = indicators.perf_stats(navs)
        st.update({"code": code, "name": names[code],
                   "latest_nav": navs[-1], "source": entry["source"]})
        stats.append(st)
        ret_map[code] = {p.date: (navs[i] / navs[i - 1] - 1) if i > 0 else 0.0
                         for i, p in enumerate(pts)}

    # 相关性矩阵（按共同交易日的日收益）
    matrix = []
    valid = [s["code"] for s in stats]
    for a in valid:
        row = []
        for b in valid:
            common = sorted(set(ret_map[a]) & set(ret_map[b]))
            if len(common) < 5:
                row.append(None)
                continue
            va = np.array([ret_map[a][d] for d in common])
            vb = np.array([ret_map[b][d] for d in common])
            if va.std() == 0 or vb.std() == 0:
                row.append(None)
            else:
                row.append(round(float(np.corrcoef(va, vb)[0, 1]), 2))
        matrix.append(row)

    stats.sort(key=lambda x: x["total_return"], reverse=True)
    return {"days": days, "series": series, "stats": stats,
            "codes": valid, "names": [names[c] for c in valid],
            "correlation": matrix}


# ---------------- 批量历史净值（走势图数据源） ----------------
@app.get("/api/history")
def history(codes: str = Query(..., description="逗号分隔的基金代码"),
            days: int = Query(120, ge=20, le=600)):
    """返回多只基金的原始历史净值序列，供总览/走势图绘制（支持原始净值或归一化）。"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:8]
    if not code_list:
        raise HTTPException(status_code=400, detail="请至少选择一只基金")
    series = []
    for code in code_list:
        meta = watchlist.get(code) or fund_universe.get_info(code) or {"name": code}
        entry = ensure_fund(code, days)
        pts = _slice(entry, days)
        if not pts:
            continue
        navs = [p.nav for p in pts]
        series.append({
            "code": code,
            "name": meta.get("name", code),
            "category": meta.get("category", "") if isinstance(meta, dict) else "",
            "dates": [p.date for p in pts],
            "navs": navs,
            "acc_navs": [p.acc_nav for p in pts],
            "change_pct": [p.change_pct for p in pts],
            "source": entry["source"],
        })
    if not series:
        raise HTTPException(status_code=404, detail="所选基金均无历史净值数据")
    return {"days": days, "series": series,
            "codes": [s["code"] for s in series],
            "names": [s["name"] for s in series]}


# ---------------- 策略回测 ----------------
@app.get("/api/backtest/{code}")
def run_backtest(code: str,
                 strategy: str = Query("ma_cross", pattern="^(ma_cross|momentum|buy_hold)$"),
                 short: int = Query(5, ge=2, le=120),
                 long: int = Query(20, ge=3, le=250),
                 days: int = Query(250, ge=40, le=400),
                 fee_bps: float = Query(15.0, ge=0, le=200)):
    meta = watchlist.get(code) or fund_universe.get_info(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未找到")
    entry = ensure_fund(code, days)
    pts = _slice(entry, days)
    result = bt.run(pts, strategy=strategy, short=short, long=long, fee_bps=fee_bps)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    result.update({"code": code, "name": meta.get("name", code),
                   "data_source": entry["source"]})
    return result


# ---------------- 持仓 ----------------
def _nav_map() -> Dict[str, Dict[str, Any]]:
    nl = _fetch_news_cached()
    out: Dict[str, Dict[str, Any]] = {}
    for f in watchlist.list_all():
        st = build_state(f["code"], f, nl)
        lat = st["latest"]
        out[f["code"]] = {
            "name": f["name"], "nav": lat.nav if lat else None,
            "day_change_pct": lat.change_pct if lat else None,
            "advice": st["rec"].advice, "direction": st["pred"]["direction"],
        }
    # 持仓中但不在自选的基金也要取净值
    for h in portfolio.list_all():
        if h["code"] in out:
            continue
        info = fund_universe.get_info(h["code"]) or {"name": h.get("name", h["code"])}
        entry = ensure_fund(h["code"])
        pts = entry["points"]
        lat = pts[-1] if pts else None
        out[h["code"]] = {
            "name": info["name"], "nav": lat.nav if lat else None,
            "day_change_pct": lat.change_pct if lat else None,
            "advice": None, "direction": None,
        }
    return out


@app.get("/api/portfolio")
def get_portfolio():
    return portfolio.compute(_nav_map())


@app.post("/api/portfolio")
def upsert_holding(req: HoldingRequest):
    name = req.name
    if not name:
        meta = watchlist.get(req.code) or fund_universe.get_info(req.code)
        name = (meta or {}).get("name", req.code)
    try:
        portfolio.upsert(req.code.strip(), req.shares, req.cost_nav, name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return portfolio.compute(_nav_map())


@app.delete("/api/portfolio/{code}")
def delete_holding(code: str):
    if not portfolio.remove(code):
        raise HTTPException(status_code=404, detail="未找到该持仓")
    return portfolio.compute(_nav_map())


# ---------------- 新闻 ----------------
@app.get("/api/news", response_model=NewsList)
def get_news(q: Optional[str] = None, sentiment: Optional[str] = None,
             tag: Optional[str] = None, sort: str = "relevance",
             limit: int = Query(30, ge=1, le=100)):
    nl = _fetch_news_cached()
    return news_mod.filter_news(nl, q=q, sentiment=sentiment, tag=tag,
                               sort=sort, limit=limit)


@app.get("/api/news/sources")
def get_news_sources():
    return {"builtin": config.NEWS_SOURCES, "custom": news_mod.list_sources()}


@app.post("/api/news/sources")
def add_news_source(payload: Dict[str, str]):
    try:
        item = news_mod.add_source(payload.get("name", ""), payload.get("url", ""),
                                  payload.get("type", "rss"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cache.set("news", None, ttl=0)
    nl = _fetch_news_cached()
    return {"status": "added", "source": item, "news_total": nl.total,
            "note": nl.source_note}


@app.delete("/api/news/sources")
def delete_news_source(url: str):
    if not news_mod.remove_source(url):
        raise HTTPException(status_code=404, detail="未找到该新闻源")
    cache.set("news", None, ttl=0)
    return {"status": "removed", "url": url}


# ---------------- 刷新 ----------------
@app.post("/api/refresh")
def refresh():
    _fund_cache.clear()
    cache.set("news", None, ttl=0)
    nl = news_mod.get_news(limit=40)
    cache.set("news", nl, ttl=300)
    for f in watchlist.list_all():
        ensure_fund(f["code"])
    return {"status": "refreshed", "funds": len(watchlist.list_all()),
            "news": nl.total, "time": time.strftime("%H:%M:%S")}


async def _background_refresh():
    while True:
        try:
            for f in watchlist.list_all():
                ensure_fund(f["code"])
        except Exception:
            pass
        await asyncio.sleep(config.REFRESH_INTERVAL_SECONDS)


@app.on_event("startup")
async def _startup():
    fund_universe.load_universe()   # 预热基金全库（本地缓存）
    asyncio.create_task(_background_refresh())


# ---------------- 前端静态资源 ----------------
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
