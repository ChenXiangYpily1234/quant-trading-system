# Risk policy

Fund risk is computed in `backend/app/risk/metrics.py`, portfolio risk in
`backend/app/risk/portfolio.py`, and research signal risk in
`backend/app/features/volatility.py` via `signals/engine.py`. These are distinct
measures; do not conflate their scales. Empty or short series produce
`insufficient_data`. Simulated NAV is blocked before real-risk conclusions.

The agent may explain scores and enumerate inputs but may not calculate or
overwrite Sharpe, Sortino, drawdown, risk contribution, or thresholds. A
portfolio tool must require REAL data for every included holding; partial or
mixed-source aggregation is not a valid portfolio conclusion. Changing the
score formula, alert threshold, or rebalance policy needs human approval and
versioned evidence.
