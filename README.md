# QuantFlow — Fund Research & Portfolio Risk Workbench

A task-oriented fund research product for answering what changed today, why it
matters, how much risk the portfolio carries, and what deserves deeper review.
The stack remains FastAPI + SQLite + Vanilla JavaScript + ECharts.

> ⚠️ **Not investment advice.** Signals are deterministic research scores, not
> probabilities or return promises. The LLM explains validated inputs and never
> decides BUY, SELL, or position size.

## Optional QuantFlow research agent (experimental)

The original dashboard and APIs start without Codex. A separate research
gateway can launch Codex App Server over stdio and expose only validated
QuantFlow tool schemas. It does not permit real trading, production strategy
updates, holding mutations, arbitrary SQL, or an agent-side financial formula.

The gateway is disabled by default. For local, trusted testing set
`QUANTFLOW_AGENT_ENABLE=true` and a private `QUANTFLOW_AGENT_TOKEN` in the
backend environment. `QUANTFLOW_CODEX_BIN` may point to a compatible Codex
binary; on macOS the bundled Codex desktop binary is preferred when present.
Do not put the token in frontend JavaScript or expose this API publicly without
an authenticated user session and an independently verified process sandbox.

- `GET /api/agent/health` reports configuration and current-process status.
- `POST /api/agent/threads` creates an ephemeral research thread.
- `POST /api/agent/threads/{thread_id}/turns` accepts `prompt`, `page`, optional
  `fund_code`, and a research `skill`.
- `GET /api/agent/threads/{thread_id}/events?after=0` returns bounded public
  tool/final events; send `X-QuantFlow-Agent-Token` on protected routes.
- `POST /api/agent/threads/{thread_id}/turns/{turn_id}/cancel` interrupts a turn.

The agent can run scoped read tools, backtest computations/audits, and create
experiment drafts. It cannot yet execute arbitrary candidate formulas or a
historical news-sentiment experiment. Historical news availability, frozen
dataset/universe versions, out-of-sample workflow, approval UI, and production
authentication remain unimplemented. A Red Team result marks these dimensions
unverified rather than treating them as a pass. See
`docs/agent-native-migration.md` for the source audit and phase status.

---

## ✨ Features

| Capability | Description |
|------------|-------------|
| **Multi-fund monitoring** | Watch several funds at once; track NAV trajectory and short-term direction from momentum + moving-average signals. |
| **News aggregation & sentiment** | Scrape financial / CPO / tech news, score by relevance and positive/negative sentiment, sort and filter. |
| **Signal Engine** | Deterministic 0–100 trend, momentum, sentiment, risk and overall scores with explicit confidence. |
| **Risk Engine** | Volatility, downside volatility, drawdown, Sharpe, Sortino, Calmar, concentration, correlation and risk contribution. |
| **AI explanation** | Optional validated explanation layer with one retry and a deterministic fallback. It cannot make trading decisions. |
| **Rich visualization** | ECharts charts for NAV, MA5/MA20, prediction interval (confidence band) and news digest. **Red = up, green = down** (A-share convention). |
| **Historical NAV trends** | Overview trend panel with time-range / normalized-vs-raw toggles and zoomable time axis. |
| **Enhanced risk metrics** | Per-fund `perf_stats`: total / annualized return, annualized volatility, **max drawdown, Sharpe, Sortino, Calmar, downside deviation, win-rate**. |
| **Valuation temperature** | NAV-vs-long-MA percentile → a 0–100 "temperature" with a 低估 / 适中 / 高估 (under / fair / over-valued) label, shown as a badge on cards and in detail. |
| **DCA backtest** | Regular (fixed-amount) and smart (value-averaging) dollar-cost-averaging backtest with cumulative principal, final value, total return and money-weighted annualized return (XIRR). |
| **Portfolio research** | Portfolio value and P&L plus risk analysis. Rebalancing is rejected unless all required market data is REAL. |
| **Provenance boundary** | Every NAV payload is marked REAL, STALE, or SIMULATED with provider and timestamps. Simulated data is blocked from signals, backtests and rebalancing. |
| **SQLite persistence** | Watchlist and holdings use SQLite WAL; existing JSON migrates only into an empty database and is retained as `.bak`. |

---

## 🏗️ Architecture

The current decision chain is `market data → deterministic features → Signal
Engine → Risk Engine → AI explanation`. Signal cache keys include fund code,
NAV data timestamp, and signal version. The home page consumes the aggregate
`GET /api/dashboard` response. The diagram below also shows retained legacy
adapters used by the existing detail and chart features.

```
                         ┌─────────────────────────────┐
   Browser (dashboard)   │          FastAPI            │
        │                │  ┌───────────────────────┐  │
        │  REST /api/*   │  │  main.py (routes)     │  │
        ├───────────────►│  │  build_state()        │  │
        │                │  │   ├─ ensure_fund()    │  │
        │◄───────────────│  │   ├─ predictor        │  │
        │   JSON + HTML  │  │   ├─ llm (or rule)    │  │
        └───────────────►│  │   └─ intraday_estimate│  │
                         │  └───────────────────────┘  │
                         │  caches: _fund_cache         │
                         │          _state_cache        │
                         │  background refresh loop     │
                         └───────┬───────────┬──────────┘
                                 │           │
                  ┌──────────────┴──┐   ┌─────┴──────────────┐
                  │ East Money NAV │   │ News sources (RSS/  │
                  │  (real, w/     │   │  API) + built-in    │
                  │   simulated    │   │  sample fallback)   │
                  │   fallback)    │   └──────────────────────┘
                  └───────────────┘
                                 │ (optional)
                          ┌──────┴─────────┐
                          │ OpenAI-compat. │
                          │ LLM endpoint   │
                          └────────────────┘

   Frontend: index.html + css/styles.css + js/{dashboard,api,state,app}.js + lib/echarts.min.js
   (served as static files from /static; no build step required)
```

### Request flow (hot path)

1. Browser loads `/` → `index.html` (static).
2. `js/dashboard.js` calls `/api/dashboard`; retained workspaces use compatible
   legacy endpoints.
3. `list_funds()` → for each watched fund → `build_state()`.
4. `build_state()` returns the **cached** assembled state if fresh
   (`_state_cache`, TTL 60s); otherwise it computes:
   - `ensure_fund()` → NAV series from `_fund_cache` (East Money real data,
     simulated fallback), TTL 600s.
   - `signals.compute_signal()` → deterministic, versioned research scores.
   - `risk` → fund and portfolio metrics; missing inputs fail closed.
   - `ai.explain()` → schema-validated explanation, never a trade decision.
   - `intraday_estimate()` → simulated intraday valuation.
5. Prewarming runs outside the startup critical path and is overlap-guarded, so
   a slow external provider cannot prevent the service from starting.

---

## 📁 Project structure

```
quant-trading-system/
├── LICENSE
├── README.md
├── .github/
│   └── workflows/ci.yml        # CI: syntax check + boot + /api/health smoke test
├── backend/
│   ├── requirements.txt        # fastapi, uvicorn, httpx, numpy
│   ├── run.py                  # convenience launcher
│   └── app/
│       ├── config.py           # funds / news / LLM / refresh (env-overridable)
│       ├── main.py             # FastAPI routes + caches + background refresh
│       ├── fund_data.py        # NAV fetch (East Money) + simulate + intraday est.
│       ├── fund_universe.py    # local fund-code universe for search
│       ├── news.py             # news fetch (RSS/API) + built-in sample + scoring
│       ├── features/           # deterministic feature functions
│       ├── signals/            # versioned Signal Engine + schema
│       ├── risk/               # fund / portfolio metrics and alerts
│       ├── ai/                 # explanation, summary, prompts and schemas
│       ├── db/                 # SQLite WAL repository and JSON migration
│       ├── data/               # data provenance contract
│       ├── predictor.py        # legacy-compatible chart calculations
│       ├── llm.py              # compatibility adapter to ai/
│       ├── indicators.py       # MA / RSI / BOLL / MACD / volatility + perf_stats + valuation_temperature
│       ├── backtest.py         # ma_cross / momentum / buy_hold strategies
│       ├── dca.py              # dollar-cost-averaging backtest (normal / value_avg)
│       ├── rebalance.py        # equal / risk-parity / signal target weights
│       ├── portfolio.py        # holdings + P&L computation
│       ├── watchlist.py        # watched funds store
│       ├── cache.py            # simple TTL in-memory cache
│       └── schemas.py          # response models
└── frontend/
    ├── index.html              # shell with 5 task-oriented spaces
    ├── css/styles.css
    ├── js/dashboard.js         # task-first home
    ├── js/{api,state}.js       # shared frontend primitives
    ├── js/app.js               # retained workspace compatibility
    └── lib/echarts.min.js      # bundled chart library (offline-capable)
```

> `backend/data/` (cached universe) and `__pycache__/` are git-ignored.

---

## 🚀 Local run

```bash
# 1. Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Start (default 127.0.0.1:8000)
python run.py
#    or, explicitly:
#    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Open the dashboard
open http://localhost:8000
```

The dashboard auto-refreshes every 15s (configurable) and also offers a
**manual refresh** button.

---

## ⚙️ Configuration

All tunables live in `backend/app/config.py` and can be overridden by
environment variables.

### Watched funds — `DEFAULT_FUNDS`
```python
{"code": "008086", "name": "华夏中证5G通信主题ETF联接A",
 "category": "CPO/通信", "note": "...", "focus": True}
```
`code` is the East Money / Tian Tian fund code; the system tries to fetch its
real NAV automatically.

### News sources — `NEWS_SOURCES`

Five built-in RSS feeds are enabled by default, each with its own **rule
keywords** (`keywords`). Every fetched item is scored/tagged by matching against
that source's keyword list (rule hit), so the headline, relevance score, and
`#tag` chips you see in the UI are driven by which rules matched:

| Source | Theme | Rule keywords |
|--------|-------|---------------|
| 量子位(AI) | AI / 大模型 / 机器人 | 人工智能, AI, 大模型, 算力, 芯片, 机器人, 半导体, 自动驾驶 |
| 钛媒体 | 科技 / 财经 | 科技, AI, 半导体, 新能源, 数字经济, 算力, 互联网 |
| 少数派 | 数码 / 效率 / AI | 科技, 数码, AI, 软件, 效率, 智能 |
| 英为财情(市场) | 全球市场 | 股市, 基金, A股, 港股, 美股, 美联储, 黄金, 汇率, 央行, 通胀 |
| 雷锋网 | 硬科技 / 机器人 / 芯片 | 人工智能, AI, 机器人, 芯片, 半导体, 自动驾驶, 智能硬件, 算力, 新能源 |

A global keyword list `NEWS_KEYWORDS` (CPO, 光模块, 算力, 半导体, 英伟达…) is
used for the built-in sample library and as the default when a source omits
`keywords`. Append your own financial feeds — both `rss` and `api` are supported:

```python
{"type": "rss", "name": "My RSS", "url": "https://example.com/feed.xml",
 "keywords": ["CPO", "光模块"]}
```

If a feed is unreachable or returns malformed XML, the parser falls back to a
tolerant regex extractor; if **no** source returns items, the system falls back
to the built-in sample news library (clearly labeled) so the page is never
empty.

### LLM — `LLM_CONFIG` (env vars)
```bash
export OPENAI_API_KEY="sk-..."                       # enables real LLM
export OPENAI_BASE_URL="https://api.openai.com/v1"  # any OpenAI-compatible endpoint
export OPENAI_MODEL="gpt-4o-mini"
```
With a key set, an explicit “update AI explanation” action may call the model.
Dashboard and list requests always use the deterministic explanation template,
so browsing never fans out into one model request per fund. Model output is
schema-validated, retried once, then replaced by a deterministic fallback.

### Refresh / cache
| Variable | Default | Meaning |
|----------|---------|---------|
| `REFRESH_INTERVAL` | `15` | background refresh interval (seconds) |
| `HISTORY_DAYS` | `60` | default NAV history window |
| `PREDICT_DAYS` | `5` | forecast horizon (days) |
| `CACHE_TTL_SECONDS` | `60` | assembled state cache TTL |
| `FUND_CACHE_TTL` | `600` | raw NAV cache TTL (seconds) |
| `LLM_COOLDOWN` | `300` | LLM circuit-breaker cooldown (seconds) |
| `ALLOW_SIM` | `true` | allow simulated NAV when real fetch fails |
| `REQUEST_TIMEOUT` | `10` | per-request HTTP timeout (seconds) |

---

## 📡 API reference

Base URL: `http://localhost:8000`

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service status, LLM switch, counts. |
| POST | `/api/refresh` | Force-refresh all data (clears caches). |

### Funds
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/funds` | Multi-fund monitoring summaries (NAV / estimate / direction / confidence / advice). |
| GET | `/api/dashboard` | One aggregate payload for the task-first home. |
| GET | `/api/funds/search?q=` | Search funds (replaces deprecated `/api/search`). |
| GET | `/api/funds/{code}/signals` | Deterministic signal scores and provenance. |
| GET | `/api/funds/{code}/risk` | Fund risk metrics and provenance. |
| GET | `/api/funds/{code}/news` | News scoped for the fund detail workspace. |
| POST | `/api/funds` | Add a fund (`{code, category?, note?, focus?}`). |
| DELETE | `/api/funds/{code}` | Remove a fund. |
| POST | `/api/funds/{code}/focus` | Toggle focus (star) flag. |
| GET | `/api/funds/{code}` | Single-fund detail (history, MA, prediction, recommendation, sentiment). |
| GET | `/api/analysis/{code}` | LLM / rule-engine analysis result. |
| GET | `/api/export/{code}.csv` | Export NAV + indicators as CSV. |
| POST | `/api/watchlist/reset` | Reset watchlist to defaults. |

### Discovery & comparison
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/search?q=` | Search the fund universe by code / name / pinyin. |
| GET | `/api/compare?codes=a,b&days=` | Compare multiple funds (normalized return, correlation matrix). |
| GET | `/api/history?codes=a,b&days=` | Raw historical NAV series for the trend chart. |

### Strategy & portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/backtest/{code}?strategy=` | Backtest (`ma_cross` / `momentum` / `buy_hold`). |
| POST | `/api/backtests` | Preferred backtest API; supports all cost fields and benchmark output. |
| GET | `/api/dca/{code}?strategy=&freq=&amount=&days=&fee_bps=` | Dollar-cost-averaging backtest (`normal` / `value_avg`, `monthly` / `weekly`). |
| GET | `/api/rebalance?method=` | Rebalance suggestion (`equal` / `risk_parity` / `signal`) with target weights and suggested trades. |
| GET | `/api/portfolio` | Portfolio holdings + P&L. |
| GET | `/api/portfolio/risk` | Portfolio risk, concentration and contributions. |
| POST | `/api/portfolio` | Upsert a holding (`{code, shares, cost_nav, name?}`). |
| DELETE | `/api/portfolio/{code}` | Remove a holding. |

### News
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/news` | News list (relevance + sentiment sort, filterable). |
| GET | `/api/news/sources` | List configured news sources. |
| POST | `/api/news/sources` | Add a news source. |
| DELETE | `/api/news/sources?url=` | Remove a news source. |

---

## 🔧 CI / CD

`.github/workflows/ci.yml` runs on every push/PR to `main`:

1. Checkout & set up Python 3.13.
2. Install `backend/requirements.txt`.
3. **Syntax checks**: `python -m compileall app` and `node --check` on every
   frontend JS file.
4. Boot the uvicorn server in the background.
5. **Smoke test**: `curl /api/health` and assert `200` on
   `/api/funds`, `/api/history`, `/api/news`, `/api/search`.
6. Shut the server down.

This gives a push-to-`main` gate that the service boots and its core endpoints
respond before the change is considered healthy.

---

## ⚠️ Notes & boundaries

- **Real data**: NAV comes from East Money's public interface (daily frequency,
  updated after market close). When unreachable, deterministic simulated data
  may keep demo surfaces visible, but it is blocked from signals, backtests,
  rebalancing, and mixed REAL/SIMULATED comparisons.
- **Intraday estimate**: Real intraday quote APIs are not openly available, so
  the dashboard shows a **time-driven simulated valuation** clearly marked as
  "模拟估值 / simulated" — for demonstration only.
- **Signals**: Scores describe deterministic trend evidence. They are not an
  “up probability” and do **not constitute investment advice**.
- **News sources**: Direct financial-news endpoints are often anti-scraped
  protected; the default falls back to the built-in sample library. Wire your
  own permitted sources via `NEWS_SOURCES`.

---

## 📄 License

Released under the [MIT License](./LICENSE).
