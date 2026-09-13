---
name: backtest-red-team
description: Falsify a QuantFlow candidate strategy using leakage, timing, cost, benchmark, selection, sample-size, and out-of-sample checks.
---

# Backtest Red Team

Call `backtest.audit` and use its deterministic check outcomes. Produce a
structured PASS, WARNING, or FAIL verdict for each testable gate:
future information, execution timing, news timestamp alignment, leakage,
survivorship/universe bias, parameter overfitting, cherry-picked dates,
turnover and transaction costs, benchmark weakness, sample size, regime
stability, extreme markets, and risk-adjusted excess return. A missing test or
dataset is `unverified`, not PASS. Any FAIL blocks `accepted`; no red-team
result alone deploys a candidate. Use deterministic backtest evidence; do not
recalculate financial metrics in prose.
