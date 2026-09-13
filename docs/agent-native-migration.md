# Agent-native architecture migration plan

## Current architecture (source audit, 2026-09-13)

`frontend/index.html` + `frontend/js/{dashboard,app,api,state}.js` consume
FastAPI routes in `backend/app/main.py`. The hot path is:

```
East Money NAV / simulated fallback -> ensure_fund cache + provenance
  -> features/{trend,momentum,sentiment,volatility}
  -> signals/engine.py -> risk/{metrics,portfolio}.py
  -> portfolio.py / backtest.py / rebalance.py -> main.py API -> frontend
```

`main.py:build_state` also calls the legacy `predictor` and `llm` explanation
adapter. News comes from `news.py` and may degrade to built-in examples.
SQLite WAL (`db/database.py`, `db/repository.py`) currently stores watchlist,
portfolio, settings, and alerts; it has no experiment/agent tables. `cache.py`
and two `main.py` maps provide TTL caching. Existing tests cover provenance,
signals, risk, backtest execution/costs, and cache. There are five main UI
spaces plus detail/news views. Quant Core starts without Codex.

## Target and reuse

Keep the deterministic core and all legacy routes. Wrap public, validated
functions in `backend/app/agent_tools`; do not copy formulas. The best initial
READ tools are `fund_universe.search`, `ensure_fund`/NAV snapshot and history,
`compute_signal`, `calculate_metrics`, `portfolio_risk`, `news.filter_news`,
and `backtest.run`. `portfolio.list_all` may be read through a scoped tool,
but `portfolio.upsert/remove`, `watchlist` writes, news-source writes,
`db.repository`, score internals, and `rebalance.suggest` without a REAL-data
gate must not be exposed directly.

The gateway runs a separate Codex App Server process and declares only
allowlisted Quant tools. Codex owns threads/turns; the Python adapter owns
validation, provenance, audit, and approval. An agent process failure must
return a typed unavailable response, while existing APIs continue running.
No agent-facing shell or broad filesystem tools in the research runtime.

## Boundaries and changes

- Tool boundary: strict Pydantic inputs, structured results, explicit
  `insufficient_evidence` for simulated/stale/missing data. Avoid `main.py`
  route functions as tool implementations because their FastAPI defaults and
  presentation fields do not form a safe core API.
- Approval boundary: READ and research SAFE_WRITE only by default. A request
  for production/code/schema/cost/benchmark changes creates a reviewable
  approval item; the agent cannot apply it. A human executes approved changes
  through a separate controlled path.
- Database: add experiments, experiment runs, strategy versions, dataset
  versions, agent runs, and approvals with explicit lineage. Do not rewrite
  existing watchlist/portfolio tables or live holdings.
- API: additive `/api/agent/*`, `/api/experiments/*`, `/api/approvals/*` routes;
  existing routes remain compatible. Agent health is separate from `/api/health`.
- Frontend: add contextual Quant Copilot, Research, Experiments, and Approvals
  to existing Vanilla JS UI only after gateway and policy tests pass.
- Compatibility: isolate imported `codex-main/` as optional upstream source;
  no Rust core fork. The installed/built `codex app-server` is configured via
  adapter. The root `pytest` runner must collect only QuantFlow tests because
  the imported upstream tree has its own package-specific tests.

## Risks and deviations from the requested design

1. `codex-main/` is a full, untracked 91 MB Rust workspace. Crate deletion
   without a dependency graph can break App Server. Remove only verified
   ancillary files; retain build inputs and licenses.
2. Existing `signal.history` is not persisted. Historical score changes cannot
   be inferred from one current score; add a versioned snapshot store or return
   unavailable until available.
3. News fallback is sample content and publication timestamps are not yet
   adequate for backtest alignment. `news.events` cannot imply causal impact.
4. Current buy-and-hold benchmark is the same fund NAV, not an independent
   market index; label it precisely. No frozen universe, dataset lineage, or
   walk-forward engine yet exists.
5. Current `portfolio`/`dashboard` presentation paths can display simulated
   values. They must not be turned into Agent financial conclusions as-is.
6. Prompt-only approval is insufficient: enforce permissions in registry and
   server-side process sandbox, then test attempts to bypass them.

## Phases and gates

A. Audit real call paths and conflicts (this document).
B. Write contracts and repo instructions.
C. Add READ tools with schemas, provenance, policy tests; do not connect Codex.
D. Add experiment/strategy/approval persistence and fail-closed promotion.
E. Add App Server adapter, thread/turn/event gateway, and audit.
F. Add scoped researcher/auditor/portfolio/developer skills.
G. Add candidate workflow and backtest red team, with out-of-sample gate.
H. Add contextual Copilot; I. Add research/experiment/approval UI.
J. Verify all five requested end-to-end scenarios with REAL data or clearly
mark them unverified when the external runtime/provider is unavailable.

At each phase run QuantFlow pytest, Python compileall, JavaScript syntax,
FastAPI startup and API smoke, and `git diff --check`. A failed gate is fixed
before proceeding; a mock is not evidence of live Codex integration or
strategy validity.

## Implementation status after this pass

Phases A-F have an implemented engineering slice: contracts, tool registry,
research metadata tables, optional App Server adapter, and seven project
skills. A real App Server stdio handshake, ephemeral thread start, simple
model turn, and one `signal.get` model/tool turn were observed locally. This
does not establish production-grade sandbox isolation or financial validity.
Phase G currently has a deterministic Red Team timing/cost/benchmark audit,
but no arbitrary candidate runner, historical news dataset, or out-of-sample
experiment workflow. Therefore no candidate can be marked accepted. Phases
H-J (Copilot UI, research UI, full end-to-end acceptance) have not begun.
