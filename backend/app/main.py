"""FastAPI 主程序：聚合基金数据、预测、新闻与决策，提供 REST 接口与前端页面。"""
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import config, fund_data, news as news_mod, predictor, llm
from .cache import cache
from .schemas import (
    FundSummary, FundDetail, NewsList, NewsItem, AnalysisResult, NavPoint,
)

BASE = Path(__file__).resolve().parent.parent.parent  # .../quant-trading-system
FRONTEND = BASE / "frontend"

app = FastAPI(title="量化交易系统 · CPO/科技基金监控", version="1.0.0")

# 基金净值缓存：code -> {points, source, updated}
_fund_cache: Dict[str, Dict[str, Any]] = {}


def _fetch_news_cached() -> NewsList:
    cached = cache.get("news")
    if cached:
        return cached
    nl = news_mod.get_news(limit=20)
    cache.set("news", nl, ttl=300)
    return nl


def ensure_fund(code: str, days: int = config.HISTORY_DAYS) -> Dict[str, Any]:
    entry = _fund_cache.get(code)
    now = time.time()
    if entry and (now - entry["updated"]) < config.FUND_CACHE_TTL:
        return entry
    points, source = fund_data.get_nav(code, days)
    entry = {"points": points, "source": source, "updated": now}
    _fund_cache[code] = entry
    return entry


def build_state(code: str, meta: Dict[str, str], news_list: NewsList):
    entry = ensure_fund(code)
    points = entry["points"]
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


@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "llm_enabled": config.LLM_CONFIG["enabled"],
            "funds_monitored": len(config.DEFAULT_FUNDS)}


@app.get("/api/funds", response_model=List[FundSummary])
def list_funds():
    nl = _fetch_news_cached()
    out: List[FundSummary] = []
    for f in config.DEFAULT_FUNDS:
        st = build_state(f["code"], f, nl)
        lat = st["latest"]
        out.append(FundSummary(
            code=f["code"], name=f["name"], category=f["category"], note=f.get("note"),
            focus=f.get("focus", False),
            latest_nav=lat.nav if lat else None,
            latest_date=lat.date if lat else None,
            day_change_pct=lat.change_pct if lat else None,
            estimate_nav=st["estimate"],
            estimate_change_pct=st["estimate_change"],
            direction=st["pred"]["direction"],
            confidence=st["pred"]["confidence"],
            advice=st["rec"].advice,
            data_source=st["source"],
        ))
    return out


@app.get("/api/funds/{code}", response_model=FundDetail)
def fund_detail(code: str):
    meta = next((f for f in config.DEFAULT_FUNDS if f["code"] == code), None)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未配置")
    nl = _fetch_news_cached()
    st = build_state(code, meta, nl)
    return FundDetail(
        code=code, name=meta["name"], category=meta["category"], note=meta.get("note"),
        focus=meta.get("focus", False),
        data_source=st["source"],
        history=st["points"],
        ma5=st["pred"]["indicators"]["ma5"],
        ma20=st["pred"]["indicators"]["ma20"],
        prediction=st["pred"],
        recommendation=st["rec"].dict(),
        sentiment=st["sentiment"],
    )


@app.get("/api/news", response_model=NewsList)
def get_news():
    return _fetch_news_cached()


@app.get("/api/analysis/{code}", response_model=AnalysisResult)
def analysis(code: str):
    meta = next((f for f in config.DEFAULT_FUNDS if f["code"] == code), None)
    if not meta:
        raise HTTPException(status_code=404, detail="基金代码未配置")
    nl = _fetch_news_cached()
    st = build_state(code, meta, nl)
    return st["rec"]


@app.post("/api/refresh")
def refresh():
    _fund_cache.clear()
    cache.set("news", None, ttl=0)
    nl = news_mod.get_news(limit=20)
    cache.set("news", nl, ttl=300)
    for f in config.DEFAULT_FUNDS:
        ensure_fund(f["code"])
    return {"status": "refreshed", "funds": len(config.DEFAULT_FUNDS), "news": nl.total}


# ---------- 后台自动刷新（实时性） ----------
async def _background_refresh():
    while True:
        try:
            for f in config.DEFAULT_FUNDS:
                ensure_fund(f["code"])
        except Exception:
            pass
        await asyncio.sleep(config.REFRESH_INTERVAL_SECONDS)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_background_refresh())


# ---------- 前端静态资源 ----------
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
