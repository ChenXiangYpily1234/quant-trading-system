"""FastAPI 主程序：基金监控、预测、新闻、决策、对比、回测、持仓的统一 API 层。"""
import asyncio
import io
import csv
import time
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse

from . import (config, fund_data, news as news_mod, predictor, llm,
               indicators, backtest as bt, watchlist, portfolio, fund_universe, dca,
               rebalance as rb)
from .cache import cache
from .data.provenance import provenance, permits_research
from .signals import compute_signal
from .risk.metrics import calculate_metrics
from .risk.portfolio import portfolio_risk
from .ai.summary import dashboard_summary
from .core.logging import event as log_event
from .agent.gateway import router as agent_router, shutdown_runtime
from .schemas import (
    FundSummary, FundDetail, NewsList, AnalysisResult,
    AddFundRequest, HoldingRequest,
)

BASE = Path(__file__).resolve().parent.parent.parent  # .../quant-trading-system
FRONTEND = BASE / "frontend"

@asynccontextmanager
async def lifespan(_: FastAPI):
    fund_universe.load_universe()
    warm_task = asyncio.create_task(asyncio.to_thread(_warm_all))
    refresh_task = asyncio.create_task(_background_refresh())
    try:
        yield
    finally:
        warm_task.cancel()
        refresh_task.cancel()
        await asyncio.gather(warm_task, refresh_task, return_exceptions=True)
        await shutdown_runtime()


app = FastAPI(title="QuantFlow · 基金投资分析工作台", version="3.0.0", lifespan=lifespan)
app.include_router(agent_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event("request_failed", request_id=request_id, path=request.url.path,
                  latency_ms=round((time.perf_counter() - started) * 1000, 2), error=type(exc).__name__)
        raise
    response.headers["X-Request-ID"] = request_id
    log_event("request_complete", request_id=request_id, path=request.url.path,
              status=response.status_code, latency_ms=round((time.perf_counter() - started) * 1000, 2))
    return response


@app.exception_handler(HTTPException)
async def unified_http_error(_: Request, exc: HTTPException):
    message = str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={
        "success": False, "detail": message,
        "error": {"code": "REQUEST_REJECTED", "message": message,
                  "retryable": exc.status_code >= 500},
    })

# 基金净值缓存：code -> {points, source, updated, days}
_fund_cache: Dict[str, Dict[str, Any]] = {}
# 组装状态缓存：(code, days) -> {state, updated}；避免每个请求都重跑预测+LLM 研判
_state_cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
_warm_lock = threading.Lock()


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
    entry = {"points": points, "source": source, "updated": now, "days": want,
             "provenance": provenance(source, "eastmoney" if source == "REAL" else "quantflow-demo",
                                      points[-1].date if points else None)}
    _fund_cache[code] = entry
    log_event("fund_data_loaded", fund_code=code, provider=entry["provenance"]["provider"],
              data_timestamp=entry["provenance"]["data_timestamp"], data_source=source,
              signal_version=config.SIGNAL_VERSION)
    if source != "REAL":
        log_event("real_data_degraded", fund_code=code, provider="eastmoney", data_source=source)
    return entry


def _slice(entry: Dict[str, Any], days: int):
    pts = entry["points"]
    return pts[-days:] if days and len(pts) > days else pts


def build_state(code: str, meta: Dict[str, str], news_list: NewsList,
                days: int = config.HISTORY_DAYS):
    # Signal 缓存键绑定数据版本与算法版本；NAV 更新后不会复用旧信号。
    entry = ensure_fund(code, days)
    key = (code, days, entry["provenance"].get("data_timestamp"), config.SIGNAL_VERSION)
    now = time.time()
    cached = _state_cache.get(key)
    if cached and (now - cached["updated"]) < config.CACHE_TTL_SECONDS:
        return cached["state"]
    points = _slice(entry, days)
    source = entry["source"]
    sentiment = predictor.aggregate_news_sentiment(news_list.items)
    navs = [p.nav for p in points]
    # 新闻发布时间尚未完成 NAV 日期可用性对齐；研究信号统一使用中性情绪。
    signal = compute_signal(navs, [], source)
    risk = calculate_metrics(navs) if permits_research(source) else {"status": "blocked_simulated_data"}
    if risk.get("status") == "ok":
        risk_score = signal.risk_score or 0
        risk["risk_score"] = risk_score
        risk["risk_level"] = "high" if risk_score >= 67 else ("medium" if risk_score >= 34 else "low")
    if permits_research(source):
        pred = predictor.predict(code, points, sentiment)
    else:
        pred = {"direction": "flat", "confidence": 0.0, "predicted_change_pct": None,
                "predicted_nav": None, "future_dates": [], "future_nav": [],
                "future_upper": [], "future_lower": [], "indicators": predictor.compute_indicators(points),
                "rationale": "模拟数据仅供界面演示，不生成研究信号。"}
    pred["signal"] = signal.model_dump()
    pred["risk"] = risk
    rec = llm.analyze(code, meta["name"], pred, news_list.items)
    est, est_chg = fund_data.intraday_estimate(code, pred["indicators"]["latest_nav"], source)
    latest = points[-1] if points else None
    state = {
        "points": points, "source": source, "sentiment": sentiment,
        "pred": pred, "rec": rec, "estimate": est, "estimate_change": est_chg,
        "latest": latest, "signal": signal.model_dump(), "risk": risk,
        "provenance": entry["provenance"],
    }
    _state_cache[key] = {"state": state, "updated": now}
    return state


def _valuation_of(code: str) -> Optional[Dict[str, Any]]:
    """取较长窗口净值序列计算估值温度（带缓存）。"""
    try:
        entry = ensure_fund(code, max(config.HISTORY_DAYS, 250))
        return indicators.valuation_temperature([p.nav for p in entry["points"]])
    except Exception:
        return None


def _summary_of(f: Dict[str, Any], nl: NewsList, held_codes: set) -> FundSummary:
    st = build_state(f["code"], f, nl)
    lat = st["latest"]
    pts = st["points"]
    navs = [p.nav for p in pts]
    ret20 = round((navs[-1] / navs[-21] - 1) * 100, 2) if len(navs) >= 21 else (
        round((navs[-1] / navs[0] - 1) * 100, 2) if navs else None)
    risk = indicators.perf_stats(navs) if len(navs) >= 2 else None
    valuation = _valuation_of(f["code"])
    return FundSummary(
        code=f["code"], name=f["name"], category=f.get("category", "其他"),
        note=f.get("note"), focus=f.get("focus", False),
        latest_nav=lat.nav if lat else None,
        latest_date=lat.date if lat else None,
        day_change_pct=lat.change_pct if lat else None,
        estimate_nav=st["estimate"], estimate_change_pct=st["estimate_change"],
        direction={"positive": "up", "negative": "down"}.get(st["signal"].get("state"), "flat"),
        confidence=st["signal"].get("confidence", 0),
        advice=st["rec"].advice, position_action=st["rec"].position_action,
        risk_level=st["rec"].risk_level,
        predicted_change_pct=st["pred"]["predicted_change_pct"],
        return_20d=ret20,
        risk=risk,
        valuation=valuation,
        sparkline=[round(v, 4) for v in navs[-30:]],
        data_source=st["source"], provenance=st.get("provenance", {}) or ensure_fund(f["code"])["provenance"],
        signal=st["signal"],
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
    for k in [k for k in _state_cache if k[0] == code]:
        _state_cache.pop(k, None)
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
    _state_cache.clear()
    return {"status": "reset", "count": len(data)}


@app.get("/api/search", deprecated=True)
def search_funds(q: str = Query("", description="基金代码/名称/拼音"),
                 limit: int = 15):
    results = fund_universe.search(q, limit=limit)
    owned = set(watchlist.codes())
    for r in results:
        r["added"] = r["code"] in owned
    return {"query": q, "count": len(results), "results": results,
            "universe_size": fund_universe.universe_size()}


@app.get("/api/funds/search")
def search_funds_v2(q: str = Query(""), limit: int = 15):
    """替代旧 /api/search；旧路径仍保留兼容。"""
    return search_funds(q=q, limit=limit)


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
        valuation=_valuation_of(code),
        prediction=st["pred"],
        recommendation=st["rec"].dict(),
        sentiment=st["sentiment"],
        provenance=ensure_fund(code, days)["provenance"], signal=st["signal"], risk=st["risk"],
    )


@app.get("/api/analysis/{code}", response_model=AnalysisResult, deprecated=True)
def analysis(code: str, force: bool = False):
    meta = watchlist.get(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未配置")
    if force:
        _fund_cache.pop(code, None)
        cache.set("news", None, ttl=0)
    nl = _fetch_news_cached()
    st = build_state(code, meta, nl)
    if force:
        return llm.analyze(code, meta["name"], st["pred"], nl.items, allow_llm=True)
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

    sources = {item["source"] for item in stats}
    if len(sources) > 1:
        raise HTTPException(status_code=409, detail="REAL 与 SIMULATED 数据禁止混合比较")

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
            "provenance": entry["provenance"],
        })
    if not series:
        raise HTTPException(status_code=404, detail="所选基金均无历史净值数据")
    if len({item["source"] for item in series}) > 1:
        raise HTTPException(status_code=409, detail="REAL 与 SIMULATED 数据禁止混合展示")
    return {"days": days, "series": series,
            "codes": [s["code"] for s in series],
            "names": [s["name"] for s in series]}


# ---------------- 策略回测 ----------------
@app.get("/api/backtest/{code}", deprecated=True)
def run_backtest(code: str,
                 strategy: str = Query("ma_cross", pattern="^(ma_cross|momentum|buy_hold)$"),
                 short: int = Query(5, ge=2, le=120),
                 long: int = Query(20, ge=3, le=250),
                 days: int = Query(250, ge=40, le=400),
                 fee_bps: float = Query(15.0, ge=0, le=200),
                 subscription_fee: float = Query(config.SUBSCRIPTION_FEE, ge=0, le=0.1),
                 redemption_fee: float = Query(config.REDEMPTION_FEE, ge=0, le=0.1),
                 management_fee: float = Query(config.MANAGEMENT_FEE, ge=0, le=0.1),
                 transaction_cost: float = Query(config.TRANSACTION_COST, ge=0, le=0.1)):
    meta = watchlist.get(code) or fund_universe.get_info(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未找到")
    entry = ensure_fund(code, days)
    if not permits_research(entry["source"]):
        log_event("backtest_rejected", fund_code=code, data_source=entry["source"], error="simulated_data")
        raise HTTPException(status_code=409, detail="实时数据暂时不可用；模拟数据禁止进入真实回测")
    pts = _slice(entry, days)
    result = bt.run(pts, strategy=strategy, short=short, long=long, fee_bps=fee_bps,
                    subscription_fee=subscription_fee, redemption_fee=redemption_fee,
                    management_fee=management_fee, transaction_cost=transaction_cost)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    result.update({"code": code, "name": meta.get("name", code),
                   "data_source": entry["source"]})
    return result


# ---------------- 定投回测 ----------------
@app.get("/api/dca/{code}")
def run_dca(code: str,
            strategy: str = Query("normal", pattern="^(normal|value_avg)$"),
            freq: str = Query("monthly", pattern="^(monthly|weekly)$"),
            amount: float = Query(1000.0, ge=10, le=100000),
            days: int = Query(250, ge=40, le=400),
            fee_bps: float = Query(15.0, ge=0, le=200)):
    """定投回测：普通定投 / 智能定投（价值平均），输出累计本金、期末市值、收益率、XIRR。"""
    meta = watchlist.get(code) or fund_universe.get_info(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未找到")
    entry = ensure_fund(code, days)
    if not permits_research(entry["source"]):
        raise HTTPException(status_code=409, detail="实时数据暂时不可用；模拟数据禁止进入真实回测")
    pts = _slice(entry, days)
    if len(pts) < 10:
        raise HTTPException(status_code=400,
                            detail="历史数据不足，无法定投回测")
    result = dca.run(pts, amount=amount, freq=freq, strategy=strategy, fee_bps=fee_bps)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    result.update({"code": code, "name": meta.get("name", code),
                   "data_source": entry["source"]})
    return result


# ---------------- 组合再平衡 ----------------
@app.get("/api/rebalance")
def rebalance(method: str = Query("risk_parity",
                                   pattern="^(equal|risk_parity|signal)$")):
    """组合再平衡建议：equal（等权）/ risk_parity（风险平价）/ signal（信号加权）。
    基于当前持仓市值、各基金年化波动率与预测信号，给出目标权重与建议调仓。"""
    holdings = portfolio.list_all()
    if not holdings:
        raise HTTPException(status_code=400,
                            detail="请先添加持仓（POST /api/portfolio）后再做再平衡")
    nl = _fetch_news_cached()
    navs: Dict[str, float] = {}
    vols: Dict[str, float] = {}
    prices: Dict[str, float] = {}
    signals: Dict[str, Dict[str, Any]] = {}
    for h in holdings:
        code = h["code"]
        info = fund_universe.get_info(code) or {"name": h.get("name", code)}
        entry = ensure_fund(code, max(config.HISTORY_DAYS, 250))
        if not permits_research(entry["source"]):
            raise HTTPException(status_code=409, detail="实时数据暂时不可用；模拟数据禁止生成组合调整建议")
        pts = entry["points"]
        navv = [p.nav for p in pts]
        meta = {"code": code, "name": info.get("name", code),
                "category": info.get("type", ""), "note": "", "focus": False}
        st = build_state(code, meta, nl)
        cur = st["latest"]
        price = cur.nav if cur else (navv[-1] if navv else 0.0)
        shares = float(h["shares"])
        value = shares * price if price else 0.0
        navs[code] = value
        prices[code] = price
        vols[code] = (indicators.perf_stats(navv).get("volatility") or 0.0) / 100.0
        signals[code] = {"direction": {"positive": "up", "negative": "down"}.get(
                            st["signal"].get("state"), "flat"),
                         "confidence": st["signal"].get("confidence") or 0.0}
    if not any(navs.values()):
        raise HTTPException(status_code=400, detail="持仓暂无净值数据，无法再平衡")

    def _resolve_name(h):
        nm = h.get("name")
        if nm:
            return nm
        info = fund_universe.get_info(h["code"]) or {}
        if isinstance(info, dict):
            return info.get("name", h["code"])
        return str(info) if info else h["code"]

    names = {h["code"]: _resolve_name(h) for h in holdings}
    return rb.suggest(method, navs, vols, signals, prices, names)
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
    _state_cache.clear()
    cache.set("news", None, ttl=0)
    nl = news_mod.get_news(limit=40)
    cache.set("news", nl, ttl=300)
    for f in watchlist.list_all():
        ensure_fund(f["code"])
    return {"status": "refreshed", "funds": len(watchlist.list_all()),
            "news": nl.total, "time": time.strftime("%H:%M:%S")}


# ---------------- QuantFlow 任务导向 API（旧 API 保留兼容） ----------------
@app.get("/api/funds/{code}/signals")
def fund_signals(code: str, days: int = Query(60, ge=20, le=400)):
    detail = fund_detail(code, days)
    return {"code": code, "signal": detail.signal, "provenance": detail.provenance}


@app.get("/api/funds/{code}/risk")
def fund_risk(code: str, days: int = Query(250, ge=20, le=400)):
    entry = ensure_fund(code, days)
    if not permits_research(entry["source"]):
        return {"code": code, "status": "blocked_simulated_data", "provenance": entry["provenance"]}
    result = calculate_metrics([p.nav for p in _slice(entry, days)])
    return {"code": code, **result, "provenance": entry["provenance"]}


@app.get("/api/funds/{code}/news")
def fund_news(code: str, limit: int = Query(10, ge=1, le=40)):
    meta = watchlist.get(code) or fund_universe.get_info(code)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未找到")
    nl = _fetch_news_cached()
    return {"code": code, "items": [item.dict() for item in nl.items[:limit]], "total": min(limit, nl.total)}


def _portfolio_risk_payload() -> Dict[str, Any]:
    holdings = portfolio.list_all()
    if not holdings:
        return {"status": "insufficient_data", "risk_level": None, "alerts": []}
    values, returns = {}, {}
    for holding in holdings:
        entry = ensure_fund(holding["code"], 250)
        if not permits_research(entry["source"]):
            return {"status": "blocked_simulated_data", "risk_level": None, "alerts": []}
        navs = [p.nav for p in entry["points"]]
        if len(navs) < 3:
            continue
        values[holding["code"]] = holding["shares"] * navs[-1]
        returns[holding["code"]] = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs))]
    total = sum(values.values())
    weights = {code: value / total for code, value in values.items()} if total else {}
    return portfolio_risk(weights, returns)


@app.get("/api/portfolio/risk")
def get_portfolio_risk():
    return _portfolio_risk_payload()


@app.get("/api/watchlist")
def get_watchlist():
    return {"items": watchlist.list_all()}


@app.post("/api/watchlist")
def add_watchlist(req: AddFundRequest):
    return watchlist.add(req.code.strip(), req.category, req.note, req.focus)


@app.get("/api/alerts")
def get_alerts():
    return {"items": _portfolio_risk_payload().get("alerts", [])}


@app.post("/api/backtests")
def run_backtest_v2(payload: Dict[str, Any]):
    code = str(payload.get("code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="基金代码不能为空")
    return run_backtest(code, strategy=payload.get("strategy", "ma_cross"),
                        short=int(payload.get("short", 5)), long=int(payload.get("long", 20)),
                        days=int(payload.get("days", 250)), fee_bps=float(payload.get("fee_bps", 15)),
                        subscription_fee=float(payload.get("subscription_fee", config.SUBSCRIPTION_FEE)),
                        redemption_fee=float(payload.get("redemption_fee", config.REDEMPTION_FEE)),
                        management_fee=float(payload.get("management_fee", config.MANAGEMENT_FEE)),
                        transaction_cost=float(payload.get("transaction_cost", config.TRANSACTION_COST)))


@app.get("/api/dashboard")
def dashboard():
    funds = list_funds()
    pf = get_portfolio()
    pf_risk = _portfolio_risk_payload()
    changes = []
    for fund in funds:
        signal = fund.signal or {}
        if signal.get("status") == "ok" and (signal.get("overall_score", 50) >= 65 or signal.get("risk_score", 0) >= 65):
            changes.append({"code": fund.code, "name": fund.name, "state": signal.get("state"),
                            "trend_score": signal.get("trend_score"), "risk_score": signal.get("risk_score")})
    watch = [{"code": f.code, "name": f.name, "latest_nav": f.latest_nav,
              "day_change_pct": f.day_change_pct, "signal": f.signal,
              "data_source": f.data_source} for f in funds if f.focus][:8]
    summary = pf.get("summary", {})
    return {"portfolio": summary, "performance": {"today_return": summary.get("day_pnl_pct"),
                "return_30d": (pf_risk.get("return_30d") * 100 if pf_risk.get("return_30d") is not None else None),
                "max_drawdown": pf_risk.get("max_drawdown")},
            "risk": pf_risk, "watchlist": watch, "alerts": pf_risk.get("alerts", []),
            "market_summary": {"important_changes": changes[:6]},
            "ai_summary": dashboard_summary(summary, pf_risk, changes[:6]),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def _warm_all():
    """预热净值与组装状态缓存，使首屏请求即时返回（后台执行，失败不阻塞）。"""
    if not _warm_lock.acquire(blocking=False):
        return
    try:
        nl = _fetch_news_cached()
        for f in watchlist.list_all():
            try:
                ensure_fund(f["code"])
            except Exception:
                pass
        for f in watchlist.list_all():
            try:
                build_state(f["code"], f, nl)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        _warm_lock.release()


async def _background_refresh():
    while True:
        await asyncio.sleep(config.REFRESH_INTERVAL_SECONDS)
        await asyncio.to_thread(_warm_all)


# ---------------- 前端静态资源 ----------------
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
