# Quant Trading System — CPO / Tech-Fund Monitoring & Decision Workbench

A self-contained quantitative monitoring and auxiliary-decision system for
**tech-themed funds** (CPO / optical modules, semiconductors, AI, 5G
communications). It continuously tracks NAV trends, scrapes financial news,
produces short-term directional predictions, and (optionally) uses an LLM to
generate actionable adjustment advice — all rendered in an interactive
dashboard.

> ⚠️ **Not investment advice.** Predictions and recommendations are derived from
> historical statistics and news sentiment. Use at your own risk.

---

## ✨ Features

| Capability | Description |
|------------|-------------|
| **Multi-fund monitoring** | Watch several funds at once; track NAV trajectory and short-term direction from momentum + moving-average signals. |
| **News aggregation & sentiment** | Scrape financial / CPO / tech news, score by relevance and positive/negative sentiment, sort and filter. |
| **LLM-assisted decisions** | Optional OpenAI-compatible model. Without an API key it transparently falls back to a built-in **rule-engine analyst**. |
| **Adjustment advice** | Clear buy / sell / add / reduce / hold suggestions plus position actions and a risk level. |
| **Rich visualization** | ECharts charts for NAV, MA5/MA20, prediction interval (confidence band) and news digest. **Red = up, green = down** (A-share convention). |
| **Historical NAV trends** | Overview trend panel with time-range / normalized-vs-raw toggles and zoomable time axis. |
| **Enhanced risk metrics** | Per-fund `perf_stats`: total / annualized return, annualized volatility, **max drawdown, Sharpe, Sortino, Calmar, downside deviation, win-rate**. |
| **Valuation temperature** | NAV-vs-long-MA percentile → a 0–100 "temperature" with a 低估 / 适中 / 高估 (under / fair / over-valued) label, shown as a badge on cards and in detail. |
| **DCA backtest** | Regular (fixed-amount) and smart (value-averaging) dollar-cost-averaging backtest with cumulative principal, final value, total return and money-weighted annualized return (XIRR). |
| **Portfolio rebalancing** | Suggest target weights via **equal-weight / risk-parity / signal-weighted** schemes and the trades needed to get there. |
| **Resilience** | Graceful degradation when external services are unreachable (simulated NAV / built-in sample news / rule engine). System stays usable. |
| **Performance** | Assembled fund state is cached and warmed on startup; an LLM circuit-breaker avoids repeated doomed network calls. Steady-state `/api/funds` is sub-10ms. |

---

## 🏗️ Architecture

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

   Frontend: index.html + css/styles.css + js/app.js + lib/echarts.min.js
   (served as static files from /static; no build step required)
```

### Request flow (hot path)

1. Browser loads `/` → `index.html` (static).
2. `js/app.js` calls `/api/funds` (and other endpoints) on load and on a timer.
3. `list_funds()` → for each watched fund → `build_state()`.
4. `build_state()` returns the **cached** assembled state if fresh
   (`_state_cache`, TTL 60s); otherwise it computes:
   - `ensure_fund()` → NAV series from `_fund_cache` (East Money real data,
     simulated fallback), TTL 600s.
   - `predictor.predict()` → momentum / MA / RSI / volatility signals.
   - `llm.analyze()` → LLM if configured & reachable, else rule engine.
   - `intraday_estimate()` → simulated intraday valuation.
5. A background task keeps `_fund_cache` and `_state_cache` warm every
   `REFRESH_INTERVAL_SECONDS` (default 15s), so the first user request after
   startup is instant.

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
│       ├── predictor.py        # statistical prediction + news sentiment
│       ├── llm.py              # LLM decision (OpenAI-compat) / rule-engine fallback
│       ├── indicators.py       # MA / RSI / BOLL / MACD / volatility + perf_stats + valuation_temperature
│       ├── backtest.py         # ma_cross / momentum / buy_hold strategies
│       ├── dca.py              # dollar-cost-averaging backtest (normal / value_avg)
│       ├── rebalance.py        # equal / risk-parity / signal target weights
│       ├── portfolio.py        # holdings + P&L computation
│       ├── watchlist.py        # watched funds store
│       ├── cache.py            # simple TTL in-memory cache
│       └── schemas.py          # response models
└── frontend/
    ├── index.html              # dashboard shell (6 tabs)
    ├── css/styles.css
    ├── js/app.js               # data fetch / render / auto-refresh
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
With a key set, the analysis engine switches to the real model. Without it, the
built-in **rule-engine analyst** (deterministic, indicator + sentiment based) is
used. If a configured endpoint is unreachable, a **circuit breaker** disables
the LLM for `LLM_COOLDOWN_SECONDS` (default 300s) and falls back to the rule
engine automatically — so the page never hangs on a dead LLM.

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
| GET | `/api/dca/{code}?strategy=&freq=&amount=&days=&fee_bps=` | Dollar-cost-averaging backtest (`normal` / `value_avg`, `monthly` / `weekly`). |
| GET | `/api/rebalance?method=` | Rebalance suggestion (`equal` / `risk_parity` / `signal`) with target weights and suggested trades. |
| GET | `/api/portfolio` | Portfolio holdings + P&L. |
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
  updated after market close). When unreachable, the system falls back to
  deterministic simulated data and labels it accordingly.
- **Intraday estimate**: Real intraday quote APIs are not openly available, so
  the dashboard shows a **time-driven simulated valuation** clearly marked as
  "模拟估值 / simulated" — for demonstration only.
- **Predictions**: Statistical forecasts and advice are based on historical
  patterns and news sentiment and **do not constitute investment advice**.
- **News sources**: Direct financial-news endpoints are often anti-scraped
  protected; the default falls back to the built-in sample library. Wire your
  own permitted sources via `NEWS_SOURCES`.

---

## 📄 License

Released under the [MIT License](./LICENSE).
