"""Only tools listed here can cross the Agent/Quant boundary."""

from typing import Callable, Dict, Tuple, Type

from pydantic import ValidationError

from . import read
from ..core.logging import event as log_event
from .schemas import (BacktestRequest, ExperimentId, ExperimentList, FundCode,
                      FundSearch, FundWindow, HistoryWindow, NewsSearch, StrictInput, ToolResult,
                      failure, success)
from ..research.registry import ExperimentCreate, create_experiment, get_experiment, list_experiments


def _experiment_create(args):
    row = create_experiment(args)
    return success("experiment.create", {"experiment": row},
                   {"data_source": "RESEARCH_METADATA", "provider": "quantflow",
                    "data_timestamp": row["created_at"], "fetched_at": row["created_at"],
                    "algorithm_version": "experiment-registry-v1"},
                   ["草稿不是回测结果或生产策略"])


def _experiment_get(args):
    row = get_experiment(args.experiment_id)
    if row is None:
        return failure("experiment.get", "not_found", "实验不存在")
    return success("experiment.get", {"experiment": row},
                   {"data_source": "RESEARCH_METADATA", "provider": "quantflow",
                    "data_timestamp": row["created_at"], "fetched_at": row["created_at"],
                    "algorithm_version": "experiment-registry-v1"})


def _experiment_list(args):
    rows = list_experiments(args.limit)
    return success("experiment.list", {"items": rows, "count": len(rows)},
                   {"data_source": "RESEARCH_METADATA", "provider": "quantflow",
                    "data_timestamp": None, "fetched_at": None,
                    "algorithm_version": "experiment-registry-v1"})

TOOLS: Dict[str, Tuple[Type[StrictInput], Callable]] = {
    "fund.search": (FundSearch, read.fund_search),
    "fund.snapshot": (FundCode, read.fund_snapshot),
    "fund.history": (HistoryWindow, read.fund_history),
    "feature.get": (FundWindow, read.feature_get),
    "signal.get": (FundWindow, read.signal_get),
    "risk.fund": (FundWindow, read.risk_fund),
    "backtest.run": (BacktestRequest, read.backtest_run),
    "backtest.audit": (BacktestRequest, read.backtest_audit),
    "news.search": (NewsSearch, read.news_search),
    "experiment.create": (ExperimentCreate, _experiment_create),
    "experiment.get": (ExperimentId, _experiment_get),
    "experiment.list": (ExperimentList, _experiment_list),
}


def tool_specs():
    return [{"type": "namespace", "name": namespace,
             "description": "QuantFlow validated financial research tools",
             "tools": [{"type": "function", "name": name.split(".", 1)[1],
                        "description": ("Create a draft research experiment" if name == "experiment.create"
                                        else f"Read validated QuantFlow {name} evidence"),
                        "inputSchema": model.model_json_schema()}
                       for name, (model, _) in TOOLS.items() if name.startswith(namespace + ".")]}
            for namespace in sorted({name.split(".", 1)[0] for name in TOOLS})]


def invoke(name: str, arguments: dict) -> ToolResult:
    spec = TOOLS.get(name)
    if spec is None:
        return failure(name, "tool_not_allowed", "该工具不在 QuantFlow 白名单中")
    model, handler = spec
    try:
        parsed = model.model_validate(arguments)
    except ValidationError:
        return failure(name, "invalid_input", "工具输入不符合 schema")
    try:
        result = handler(parsed)
        if len(result.model_dump_json()) > 30000:
            return failure(name, "output_too_large", "结果超过 Agent 工具大小上限，请缩小查询范围")
        return result
    except Exception as exc:
        # Never return a guessed financial result or sensitive exception text.
        log_event("agent_tool_failed", tool=name, error=type(exc).__name__)
        return failure(name, "tool_unavailable", "工具执行失败；没有生成研究结果", retryable=True)
