# Agent policy

The default agent has READ tools and explicitly scoped SAFE_WRITE research
tools only. A tool call has a Pydantic input model and a structured envelope:
`success`, `tool`, `data`, `provenance`, `warnings` or a typed `error` with
`code`, `message`, and `retryable`. Failures are evidence, not prompts to guess.

The agent cannot directly access SQLite, private Python objects, arbitrary
network endpoints, shell execution, core score setters, holdings mutation, or
real trading. Production writes are absent from its tool registry. A natural
language instruction never constitutes human approval.

Human approval is required for changes to signal weights, risk thresholds,
production strategy, data sources, backtest execution, costs, benchmarks,
quant principles, database schema, and any future trading action. Approval
records must bind a concrete action and diff; approving a request is not itself
permission for an agent to bypass code review or execute a trade.

An unavailable or failing Codex App Server makes the agent capability
unavailable. It must not affect the deterministic QuantFlow API. Audit logs
record public tool names, validated inputs/results, status, and timing, but not
private chain-of-thought or secrets.
