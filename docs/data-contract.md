# Data contract

`backend/app/fund_data.py:get_nav` returns ordered `NavPoint` values plus a
source label. `backend/app/main.py:ensure_fund` adds `data_source`, `provider`,
`data_timestamp`, and `fetched_at` using `backend/app/data/provenance.py`.

- `REAL`: provider-retrieved NAV, eligible for research when dates and sample
  size are sufficient.
- `STALE`: unavailable current series; not a substitute for `REAL`.
- `SIMULATED`: generated fallback for visual demonstration only.

Tool results must preserve the original provenance and add the relevant
`algorithm_version`; never relabel synthetic data as real. Mixed REAL/SIMULATED
series are not comparable. A missing timestamp or source blocks a research
conclusion. News in `backend/app/news.py` can fall back to built-in examples;
`source_note` must be inspected and examples may not be cited as events. News
publication time is not uniformly validated, so historical news attribution
remains ineligible until availability time is verified.
