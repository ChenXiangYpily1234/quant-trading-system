# QuantFlow agent instructions

QuantFlow is a research workbench, not an automated trading system. Read
`docs/quant-principles.md` and the relevant contract before changing financial
code or exposing a new agent tool.

- Preserve the deterministic data → features → signals → risk → portfolio/backtest
  path. Do not compute financial scores in prompts or tool adapters.
- `REAL` provenance is required for research conclusions, signals, backtests,
  and rebalance proposals. `SIMULATED` is display-only; `STALE` is not current
  evidence. News sample fallbacks are never market evidence.
- Model output may explain evidence and propose experiments, but cannot change
  a score, a backtest result, live holdings, or a production strategy.
- Expose financial data only through validated `backend/app/agent_tools` functions.
  Do not hand an agent SQLite, shell, arbitrary HTTP, or direct core objects.
- Production strategy, risk, data-source, benchmark, transaction-cost, financial
  algorithm, and schema changes require human review before application.
- Keep the original FastAPI routes usable when the agent runtime is absent.
- Distinguish tested engineering behavior from actual strategy performance.

The imported `codex-main/` is an optional upstream runtime source tree. Do not
modify its Rust core or delete build dependencies merely to specialize QuantFlow.
