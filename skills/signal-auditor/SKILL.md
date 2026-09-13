---
name: signal-auditor
description: Explain a QuantFlow signal and its feature inputs, especially a claimed score change, without recalculating or editing the signal.
---

# Signal auditor

Query `signal.get`, `feature.get`, `risk.fund`, and relevant `news.search` first.
`signal.history` is not yet persisted. If asked what changed since an earlier
date, say that the earlier versioned snapshot is unavailable; do not infer a
numeric delta from a single current score. Once two comparable snapshots exist,
identify the feature with the largest verified change. News with unverified
availability time cannot be credited with causing a score move. Do not modify
scores or risk thresholds.
