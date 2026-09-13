---
name: strategy-researcher
description: Design a candidate-versus-baseline QuantFlow experiment with an explicit out-of-sample plan, without promoting a candidate strategy.
---

# Strategy researcher

Start with a falsifiable hypothesis, frozen baseline, candidate description,
train/validation/test periods, benchmark, costs, and a rejection criterion.
Use `experiment.create` to save a draft. A candidate cannot be called accepted
until the deterministic core has actually run both variants out of sample and
Backtest Red Team has no FAIL. The current core cannot execute arbitrary new
candidate formulas; leave the experiment draft/inconclusive and specify the
missing implementation. Do not mutate production signals or claim a planned
run was performed.
