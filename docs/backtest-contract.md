# Backtest contract

The existing `backend/app/backtest.py:run` supports `ma_cross`, `momentum`, and
`buy_hold`. It uses prior-day positions for next-day execution, returns a
buy-and-hold NAV benchmark, and exposes gross/net return with fees. The route
in `backend/app/main.py` rejects non-REAL input before calling it.

Agent-facing backtests must validate strategy, sample period, all costs, and
benchmark before execution. Include gross return, net return, benchmark return,
excess return, maximum drawdown, Sharpe, Sortino, and Calmar; preserve units
(legacy returns are percentages). Audit execution timing, data leakage,
survivorship and universe selection, transaction cost completeness, parameter
search, time-window selection, sample size, and out-of-sample behavior. The
current core has no frozen historical universe or independent benchmark series;
label those audit dimensions `unverified`, never `PASS` by assumption.
