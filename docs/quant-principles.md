# QuantFlow quantitative principles

1. `SIMULATED` data is for UI demonstration only and may not support a real
   financial conclusion, signal, backtest, rebalance, or portfolio decision.
   Missing or stale evidence yields `insufficient_data` or
   `insufficient_evidence`, not an invented value.
2. No look-ahead bias: a signal at date *t* may use only data available by *t*.
   Execution occurs no earlier than *t+1* in the current daily-NAV backtest.
   News must be timestamped and aligned to information availability before it
   can affect a historical feature.
3. Signal Score and Risk Score are outputs of deterministic, versioned core
   functions. An LLM must neither generate nor edit either score, backtest
   metrics, or stored financial data. It explains, plans, and audits only.
4. Every backtest has an explicit benchmark and includes transaction costs.
   Report gross return, net return, benchmark return, excess return, maximum
   drawdown, Sharpe, Sortino, and Calmar together. Null/undefined statistics
   remain null. Never show only the best parameter or cherry-picked period.
5. Candidate research needs a frozen baseline and out-of-sample validation.
   An in-sample improvement alone is not evidence for deployment.
6. Each financial claim must carry data source, provider, data timestamp,
   retrieval timestamp, and algorithm version. Do not invent missing metadata.
7. The agent may do research, simulation, backtest, and paper portfolio work;
   it may not execute a real trade. Production changes need human approval.

These are target contracts. Existing legacy endpoints may not yet satisfy all
reporting/provenance fields; the agent tool layer must fail closed instead of
silently upgrading a legacy result into a compliant conclusion.
