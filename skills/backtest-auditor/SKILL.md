---
name: backtest-auditor
description: Audit a QuantFlow backtest for timing, benchmark, costs, data quality, and overfitting; seek disconfirming evidence rather than a favorable result.
---

# Backtest auditor

Use `backtest.run` and inspect its structured metrics/provenance. Check T-signal
to T+1 execution, data leakage, look-ahead, survivorship and universe bias,
transaction costs, benchmark suitability, sample size, parameter search,
time-window selection, and out-of-sample performance. The current benchmark is
the fund's own buy-and-hold NAV; it is not an independent market index. Mark
unobservable checks `unverified`, not PASS. Do not claim a strategy is valid
from one run or replace its metrics with model calculations.
