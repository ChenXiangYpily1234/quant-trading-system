"""Thin wrappers over the existing deterministic core. No database access."""

from typing import Dict, Any

from .. import backtest, config, fund_universe
from ..data.provenance import permits_research
from ..features import momentum, trend, volatility
from ..risk.metrics import calculate_metrics
from ..signals import compute_signal
from ..research.red_team import audit_backtest
from .schemas import failure, success, ToolResult


def _entry(code: str, days: int):
    # Reuse the existing NAV cache and provenance contract without calling an API route.
    from ..main import ensure_fund, _slice
    entry = ensure_fund(code, days)
    return entry, _slice(entry, days)


def _real(tool: str, entry: Dict[str, Any], min_points: int, points) -> ToolResult | None:
    if not permits_research(entry["source"]):
        return failure(tool, "insufficient_evidence", "真实净值不可用；模拟或过期数据不能用于研究")
    if len(points) < min_points or not entry["provenance"].get("data_timestamp"):
        return failure(tool, "insufficient_data", "真实净值或时间戳不足")
    return None


def _prov(entry: Dict[str, Any], version: str) -> Dict[str, Any]:
    return {**entry["provenance"], "algorithm_version": version}


def fund_search(args) -> ToolResult:
    rows = fund_universe.search(args.q, args.limit)
    return success("fund.search", {"items": rows, "count": len(rows)},
                   {"data_source": "REFERENCE", "provider": "fund_universe",
                    "data_timestamp": None, "fetched_at": None,
                    "algorithm_version": "fund-universe-search-v1"},
                   ["基金名称/代码参考数据不是实时行情或研究结论"])


def fund_snapshot(args) -> ToolResult:
    entry, points = _entry(args.code, 60)
    blocked = _real("fund.snapshot", entry, 1, points)
    if blocked:
        return blocked
    info = fund_universe.get_info(args.code)
    return success("fund.snapshot", {"code": args.code, "name": (info or {}).get("name"),
                                     "latest": points[-1].model_dump(), "points": len(points)},
                   _prov(entry, "nav-snapshot-v1"))


def fund_history(args) -> ToolResult:
    entry, points = _entry(args.code, args.days)
    blocked = _real("fund.history", entry, 2, points)
    if blocked:
        return blocked
    return success("fund.history", {"code": args.code,
                                    "history": [point.model_dump() for point in points]},
                   _prov(entry, "nav-history-v1"))


def feature_get(args) -> ToolResult:
    entry, points = _entry(args.code, args.days)
    blocked = _real("feature.get", entry, 20, points)
    if blocked:
        return blocked
    navs = [point.nav for point in points]
    return success("feature.get", {"code": args.code, "as_of": points[-1].date,
                                   "trend_score": trend.score(navs),
                                   "momentum_score": momentum.score(navs),
                                   "volatility_risk_score": volatility.risk_score(navs),
                                   "news_sentiment_score": None},
                   _prov(entry, config.SIGNAL_VERSION),
                   ["新闻没有可验证的历史可用时间，未加入此特征快照"])


def signal_get(args) -> ToolResult:
    entry, points = _entry(args.code, args.days)
    blocked = _real("signal.get", entry, 20, points)
    if blocked:
        return blocked
    # Agent tools deliberately exclude sample/undated news. This is the same
    # deterministic Signal Engine; the missing sentiment component is neutral.
    signal = compute_signal([point.nav for point in points], [], entry["source"])
    return success("signal.get", {"code": args.code, "as_of": points[-1].date,
                                  "signal": signal.model_dump()}, _prov(entry, config.SIGNAL_VERSION),
                   ["新闻情绪因缺少可验证的时间对齐而设为中性；可能与旧页面评分不同"])


def risk_fund(args) -> ToolResult:
    entry, points = _entry(args.code, args.days)
    blocked = _real("risk.fund", entry, 3, points)
    if blocked:
        return blocked
    result = calculate_metrics([point.nav for point in points])
    if result.get("status") != "ok":
        return failure("risk.fund", "insufficient_data", "无法计算风险指标")
    return success("risk.fund", {"code": args.code, "as_of": points[-1].date,
                                 "metrics": result}, _prov(entry, "risk-metrics-v1"))


def backtest_run(args) -> ToolResult:
    entry, points = _entry(args.code, args.days)
    blocked = _real("backtest.run", entry, 40, points)
    if blocked:
        return blocked
    if args.strategy == "ma_cross" and args.short >= args.long:
        return failure("backtest.run", "invalid_input", "短均线周期必须小于长均线周期")
    result = backtest.run(points, strategy=args.strategy, short=args.short,
                          long=args.long, fee_bps=args.fee_bps,
                          subscription_fee=config.SUBSCRIPTION_FEE,
                          redemption_fee=config.REDEMPTION_FEE,
                          management_fee=config.MANAGEMENT_FEE,
                          transaction_cost=config.TRANSACTION_COST)
    if "error" in result:
        return failure("backtest.run", "insufficient_data", result["error"])
    required = ("gross_return", "net_return", "benchmark_return", "excess_return")
    ratios = ("max_drawdown", "sharpe", "sortino", "calmar")
    if any(result.get(key) is None for key in required) or any(key not in result["stats"] for key in ratios):
        return failure("backtest.run", "incomplete_metrics", "回测未返回完整合同指标")
    report = {key: result[key] for key in ("strategy", "strategy_name", "params",
              "gross_return", "net_return", "benchmark_return", "excess_return")}
    report["stats"] = result["stats"]
    report["benchmark_stats"] = result["benchmark_stats"]
    report["period"] = {"start": points[0].date, "end": points[-1].date,
                        "observations": len(points)}
    return success("backtest.run", {"code": args.code, "result": report},
                   _prov(entry, "backtest-v1"),
                   ["benchmark 为同一基金的买入持有净值；未验证样本外表现或基金池偏差"])


def backtest_audit(args) -> ToolResult:
    entry, points = _entry(args.code, args.days)
    blocked = _real("backtest.audit", entry, 40, points)
    if blocked:
        return blocked
    if args.strategy == "ma_cross" and args.short >= args.long:
        return failure("backtest.audit", "invalid_input", "短均线周期必须小于长均线周期")
    result = backtest.run(points, strategy=args.strategy, short=args.short, long=args.long,
                          fee_bps=args.fee_bps, subscription_fee=config.SUBSCRIPTION_FEE,
                          redemption_fee=config.REDEMPTION_FEE,
                          management_fee=config.MANAGEMENT_FEE,
                          transaction_cost=config.TRANSACTION_COST)
    if "error" in result:
        return failure("backtest.audit", "insufficient_data", result["error"])
    report = audit_backtest(points, result)
    return success("backtest.audit", {"code": args.code, "report": report.model_dump()},
                   _prov(entry, "backtest-red-team-v1"))


def news_search(args) -> ToolResult:
    from ..main import _fetch_news_cached
    from ..news import filter_news
    nl = _fetch_news_cached()
    if nl.source_note.startswith("内置示例资讯"):
        return failure("news.search", "insufficient_evidence", "当前只有内置示例资讯")
    result = filter_news(nl, q=args.q, limit=args.limit)
    items = [{**item.model_dump(), "summary": item.summary[:300]} for item in result.items]
    return success("news.search", {"items": items,
                                   "count": result.total},
                   {"data_source": "REAL", "provider": nl.source_note,
                    "data_timestamp": None, "fetched_at": None,
                    "algorithm_version": "news-filter-v1"},
                   ["新闻发布时间未统一验证，不可用于历史因果判断"])
