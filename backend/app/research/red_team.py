"""Deterministic backtest checks; unknown research dimensions remain unverified."""

from typing import Any, Dict, List

from pydantic import BaseModel

from ..backtest import _signals_ma, _signals_momentum
from ..schemas import NavPoint


class AuditCheck(BaseModel):
    code: str
    status: str
    detail: str


class RedTeamReport(BaseModel):
    verdict: str
    checks: List[AuditCheck]


def audit_backtest(points: List[NavPoint], result: Dict[str, Any]) -> RedTeamReport:
    checks = []

    def add(code: str, status: str, detail: str) -> None:
        checks.append(AuditCheck(code=code, status=status, detail=detail))

    navs = [point.nav for point in points]
    params = result.get("params") or {}
    strategy = result.get("strategy")
    if strategy == "ma_cross":
        expected = _signals_ma(navs, params.get("short", 5), params.get("long", 20))
    elif strategy == "momentum":
        expected = _signals_momentum(navs, params.get("short", 5))
    elif strategy == "buy_hold":
        expected = [1] * len(navs)
    else:
        expected = None
    actual = result.get("position")
    if (expected is None or not isinstance(actual, list) or
            len(actual) != len(points) or actual != [0] + expected[:-1] or
            params.get("execution") != "signal_t_execute_t_plus_1"):
        add("execution_timing", "FAIL", "持仓轨迹与 T 日信号在 T+1 执行不一致")
    else:
        add("execution_timing", "PASS", "逐日持仓与 T+1 执行轨迹一致")

    gross, net = result.get("gross_return"), result.get("net_return")
    fee_fields = ("fee_bps", "subscription_fee", "redemption_fee",
                  "management_fee", "transaction_cost")
    if gross is None or net is None or any(key not in params for key in fee_fields):
        add("transaction_cost", "FAIL", "缺少总收益、净收益或费用参数")
    elif net > gross + 0.02:
        add("transaction_cost", "FAIL", "净收益高于总收益，费用口径不一致")
    elif all(float(params[key]) == 0 for key in fee_fields):
        add("transaction_cost", "WARNING", "所有费用为零，真实交易成本未验证")
    else:
        add("transaction_cost", "PASS", "已报告总/净收益及费用参数")

    if result.get("benchmark_return") is None or not result.get("benchmark"):
        add("benchmark", "FAIL", "缺少 benchmark")
    else:
        add("benchmark", "WARNING", "benchmark 为同一基金买入持有；独立市场基准未验证")

    if len(points) < 120:
        add("sample_size", "WARNING", "少于 120 个日频净值点")
    else:
        add("sample_size", "PASS", "至少 120 个日频净值点；不代表统计显著性")
    for code, detail in (
        ("data_leakage", "没有冻结特征/数据集版本，不能排除其他泄漏"),
        ("news_timing", "没有历史新闻可用时间，不能验证新闻时间对齐"),
        ("survivorship", "没有冻结历史基金池，不能排除幸存者或选择偏差"),
        ("parameter_selection", "没有完整参数搜索记录，不能排除过拟合或时间窗口挑选"),
        ("out_of_sample", "没有独立样本外回测结果"),
        ("regime_stability", "没有跨市场状态或极端行情分层结果"),
    ):
        add(code, "WARNING", detail)

    verdict = "FAIL" if any(c.status == "FAIL" for c in checks) else "WARNING"
    return RedTeamReport(verdict=verdict, checks=checks)
